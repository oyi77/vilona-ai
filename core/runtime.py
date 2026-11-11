"""Lifecycle-owned trading runtime.

The supervisor is deliberately conservative: it is stopped by default, paper
execution is selected from configuration, and a missing signal provider yields
WAIT rather than an order.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

from agents import MarketSnapshot, Signal
from agents.judge import build_user_prompt as build_judge_prompt, parse_judge, SYSTEM_PROMPT as JUDGE_PROMPT
from agents.risk_manager import RiskVerdict, evaluate as evaluate_risk
from agents.trader import build_user_prompt as build_trader_prompt, parse_signal, SYSTEM_PROMPT as TRADER_PROMPT
from config import Config, TradingConfig
from core.events import TradeEvent
from core.health import HealthSnapshot
from core.state_db import StateDB
from trading.execution import ExecutionPort, ExecutionRequest, LiveExecutionAdapter, PaperExecutionAdapter

# KingAI-parity guards & observability (wired via config flags; zero overhead when disabled)
from trading import news_guard, session_guard
from trading.recorder import recorder
from llm import budget as llm_budget

logger = logging.getLogger(__name__)


class SignalProvider(Protocol):
    async def generate(self, snapshot: MarketSnapshot) -> Signal: ...


class WaitSignalProvider:
    async def generate(self, snapshot: MarketSnapshot) -> Signal:
        return Signal(symbol=snapshot.symbol, action="WAIT", confidence=0.0, reason="no signal provider configured")


class LLMTradingProvider:
    def __init__(self, client: Any):
        self.client = client

    async def generate(self, snapshot: MarketSnapshot) -> Signal:
        raw = await self.client.generate_signal(TRADER_PROMPT, build_trader_prompt(snapshot))
        signal = parse_signal(raw or "", snapshot.symbol)
        return signal


@dataclass
class ScanResult:
    symbol: str
    action: str
    approved: bool
    reason: str
    execution: Optional[dict] = None


class RuntimeSupervisor:
    def __init__(
        self,
        bridge: Any,
        config: Config,
        state_db: Optional[StateDB] = None,
        signal_provider: Optional[SignalProvider] = None,
        judge_client: Any = None,
    ):
        self.bridge = bridge
        self.config = config
        self.state_db = state_db or StateDB()
        self.signal_provider = signal_provider or WaitSignalProvider()
        # --- KingAI-parity guards ---
        try:
            self._session_state = session_guard.load_session('default')
        except Exception as e:
            logger.warning("session_guard load failed: %s", e)
            self._session_state = None
        self.judge_client = judge_client
        self.execution: ExecutionPort = (
            PaperExecutionAdapter(bridge)
            if config.paper_trading
            else LiveExecutionAdapter(bridge)
        )
        self.health = HealthSnapshot(
            state="stopped",
            bridge_connected=bool(getattr(bridge, "is_connected", lambda: False)()),
            active_symbols=len(config.trading.symbols),
            paper=self.execution.paper,
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.RLock()
        self._inflight: set[str] = set()
        self._emergency_stop = False

    def _event(self, kind: str, symbol: str = "", payload: Optional[dict] = None) -> None:
        try:
            self.state_db.record_event(TradeEvent(kind=kind, symbol=symbol, payload=payload or {}))
        except Exception as exc:
            logger.error("failed to persist runtime event: %s", exc)
            self.health.database_healthy = False

    def status(self) -> dict:
        with self._lock:
            return self.health.to_dict()

    def start(self) -> bool:
        with self._lock:
            if self._emergency_stop or (self._thread and self._thread.is_alive()):
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_thread, name="vilona-runtime", daemon=True)
            self._thread.start()
            self.health.state = "running"
            self.health.started_at = time.time()
            self.health.emergency_latched = False
            self.health.emergency_file_present = False
            self._event("runtime_started", payload={"paper": self.execution.paper})
            return True

    def stop(self, timeout: float = 10.0) -> bool:
        self._stop_event.set()
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(lambda: None)
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        with self._lock:
            self.health.state = "stopped" if not thread or not thread.is_alive() else "stopping"
        self._event("runtime_stopped")
        return self.health.state == "stopped"

    def emergency_stop(self, reason: str = "manual emergency stop") -> None:
        with self._lock:
            self._emergency_stop = True
            self.health.state = "emergency_stopped"
            self.health.last_error = reason
            self.health.emergency_latched = True
            self.health.emergency_file_present = Path(self.config.emergency_stop_file).exists()
        self._stop_event.set()
        self._event("emergency_stop", payload={"reason": reason})

    def reset_emergency_stop(self) -> None:
        with self._lock:
            self._emergency_stop = False
            self.health.emergency_latched = False
            self.health.emergency_file_present = False
            if self.health.state == "emergency_stopped":
                self.health.state = "stopped"

    def _run_thread(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_loop())
        finally:
            self._loop.close()
            self._loop = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set() and not self._emergency_stop:
            if Path(self.config.emergency_stop_file).exists():
                self.health.emergency_file_present = True
                self.emergency_stop("emergency-stop file detected")
                break
            started = time.monotonic()
            for symbol in self.config.trading.symbols:
                if self._stop_event.is_set():
                    break
                try:
                    await self.scan_once(symbol)
                except Exception as exc:
                    self.health.error_count += 1
                    self.health.last_error = str(exc)
                    self.health.state = "degraded"
                    self._event("system_fault", symbol, {"error": str(exc)})
                    logger.exception("scan failed for %s", symbol)
            delay = max(0.1, self.config.trading.scan_interval - (time.monotonic() - started))
            await asyncio.sleep(delay)

    @staticmethod
    def _timestamp_seconds(value: Any) -> float:
        value = float(value or 0)
        return value / 1000.0 if value > 10_000_000_000 else value

    def _snapshot(self, symbol: str) -> Optional[MarketSnapshot]:
        tick = self.bridge.get_tick(symbol)
        candles_15m = self.bridge.get_candles(symbol, "15m", limit=100) or []
        candles_1h = self.bridge.get_candles(symbol, "1h", limit=100) or []
        if not tick or len(candles_15m) < 20 or len(candles_1h) < 20:
            return None
        now = time.time()
        tick_age = now - self._timestamp_seconds(tick.timestamp_ms)
        if tick_age > self.config.trading.max_data_age_seconds:
            raise RuntimeError(f"stale tick for {symbol}: {tick_age:.1f}s")
        spread_pct = ((tick.ask - tick.bid) / tick.bid * 100.0) if tick.bid else 100.0
        ranges = [float(row["high"]) - float(row["low"]) for row in candles_15m[-20:]]
        atr = sum(ranges) / len(ranges) if ranges else 0.0
        return MarketSnapshot(symbol, float(tick.bid), float(tick.ask), candles_15m, candles_1h, spread_pct, atr, [])

    async def scan_once(self, symbol: str) -> ScanResult:
        bucket = int(time.time() // max(1, self.config.trading.scan_interval))
        key = hashlib.sha256(f"{symbol}:{bucket}".encode()).hexdigest()[:20]
        with self._lock:
            if key in self._inflight:
                return ScanResult(symbol, "WAIT", False, "duplicate scan suppressed")
            self._inflight.add(key)
            self.health.last_scan_at = time.time()
        try:
            self._event("scan_started", symbol, {"key": key})
            snapshot = self._snapshot(symbol)
            if snapshot is None:
                result = ScanResult(symbol, "WAIT", False, "market data unavailable")
                self._event("scan_skipped", symbol, {"reason": result.reason})
                return result
            positions = self.execution.get_positions(symbol)
            pl, _, _ = self.bridge.calculate_daily_pl(symbol)
            # KingAI-parity budget gate (llm/budget.py)
            over_limit, _action, _used, _limit = llm_budget.check('autotrade')
            if over_limit:
                self._event("budget_exceeded", symbol, {"used": _used, "limit": _limit})
                return ScanResult(symbol, "WAIT", False, f"daily LLM budget exceeded ({_used}/{_limit})")

            # KingAI-parity news guard (trading/news_guard.py)
            try:
                news_status = news_guard.get_zone_status(None, 30, 5)
                if news_status.zone == 'FORCE_CLOSE':
                    self._event("news_force_close", symbol, {"zone": news_status.zone})
                    return ScanResult(symbol, "WAIT", False, f"news guard: {news_status.zone}")
            except Exception as news_err:
                logger.debug("news guard skip: %s", news_err)

            signal = await self.signal_provider.generate(snapshot)
            if signal.symbol != symbol:
                signal = Signal(symbol, "WAIT", 0.0, "signal symbol mismatch")
            verdict = evaluate_risk(signal, snapshot, self.execution.get_equity(), self.config.trading, pl, len(positions))
            self._event("risk_decision", symbol, {"action": signal.action, "approved": verdict.approved, "reason": verdict.reason})
            if not verdict.approved:
                return ScanResult(symbol, signal.action, False, verdict.reason)
            if self.judge_client and signal.action != "WAIT":
                judged = await self.judge_client.generate_signal(JUDGE_PROMPT, build_judge_prompt(signal, verdict))
                approved, reason = parse_judge(judged or "")
                self._event("judge_decision", symbol, {"approved": approved, "reason": reason})
                if not approved:
                    return ScanResult(symbol, signal.action, False, f"judge veto: {reason}")
            request = ExecutionRequest(symbol, signal.action, verdict.lot_size, verdict.sl_price, verdict.tp_price, key, signal.reason)
            execution = self.execution.submit(request)
            payload = {"accepted": execution.accepted, "paper": execution.paper, "ticket": execution.ticket, "message": execution.message}
            self._event("order_filled" if execution.accepted else "order_failed", symbol, payload)
            if execution.accepted:
                self.health.last_success_at = time.time()
            return ScanResult(symbol, signal.action, execution.accepted, execution.message, payload)
        finally:
            with self._lock:
                self._inflight.discard(key)
