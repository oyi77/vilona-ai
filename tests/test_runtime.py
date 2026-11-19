from __future__ import annotations

import asyncio
import time

from agents import Signal
from config import Config, TradingConfig
from core.runtime import RuntimeSupervisor
from core.state_db import StateDB
from trading.bridge_ccxt import Tick, SymbolInfo
from trading.execution import ExecutionRequest, PaperExecutionAdapter


class RuntimeBridge:
    def __init__(self):
        self.tick = Tick("BTC/USDT", 100.0, 100.1, int(time.time() * 1000))
        self.info = SymbolInfo("BTC/USDT", point=0.01, digits=2)
        self.orders = []

    def is_connected(self):
        return True

    def get_tick(self, symbol):
        return self.tick

    def get_symbol_info(self, symbol):
        return self.info

    def get_candles(self, symbol, timeframe, limit=100):
        return [{"time": int(time.time()), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 10.0} for _ in range(limit)]

    def calculate_daily_pl(self, symbol):
        return 0.0, 0, 0

    def send_market_order(self, *args, **kwargs):
        self.orders.append((args, kwargs))
        return True, "live order", 1


def test_paper_adapter_never_calls_broker_order():
    bridge = RuntimeBridge()
    adapter = PaperExecutionAdapter(bridge, starting_equity=10000)
    result = adapter.submit(ExecutionRequest("BTC/USDT", "BUY", 0.5))
    assert result.accepted and result.paper
    assert result.fill_price == 100.1
    assert bridge.orders == []
    assert len(adapter.get_positions("BTC/USDT")) == 1


class BuyProvider:
    async def generate(self, snapshot):
        return Signal(snapshot.symbol, "BUY", 0.95, "test signal")


def test_runtime_risk_gate_executes_paper_order_and_records_events():
    bridge = RuntimeBridge()
    cfg = Config(trading=TradingConfig(symbols=["BTC/USDT"], max_data_age_seconds=120), paper_trading=True)
    db = StateDB(":memory:")
    runtime = RuntimeSupervisor(bridge, cfg, state_db=db, signal_provider=BuyProvider())
    result = asyncio.run(runtime.scan_once("BTC/USDT"))
    assert result.approved is True
    assert result.execution["paper"] is True
    assert len(runtime.execution.get_positions("BTC/USDT")) == 1
    kinds = {event["kind"] for event in db.get_events()}
    assert {"scan_started", "risk_decision", "order_filled"} <= kinds


def test_runtime_rejects_stale_market_data_without_order():
    bridge = RuntimeBridge()
    bridge.tick.timestamp_ms = 1
    cfg = Config(trading=TradingConfig(symbols=["BTC/USDT"], max_data_age_seconds=1), paper_trading=True)
    db = StateDB(":memory:")
    runtime = RuntimeSupervisor(bridge, cfg, state_db=db, signal_provider=BuyProvider())
    try:
        asyncio.run(runtime.scan_once("BTC/USDT"))
    except RuntimeError as error:
        assert "stale tick" in str(error)
    assert bridge.orders == []



class RaisingJudge:
    async def generate_signal(self, *_args):
        raise RuntimeError("judge unavailable")


class ApprovingJudge:
    async def generate_signal(self, *_args):
        return '{"verdict":"APPROVE","reason":"approved"}'


def test_runtime_vetoes_when_judge_call_raises():
    bridge = RuntimeBridge()
    cfg = Config(trading=TradingConfig(symbols=["BTC/USDT"], max_data_age_seconds=120), paper_trading=True)
    runtime = RuntimeSupervisor(bridge, cfg, state_db=StateDB(":memory:"), signal_provider=BuyProvider(), judge_client=RaisingJudge())
    result = asyncio.run(runtime.scan_once("BTC/USDT"))
    assert result.approved is False
    assert "judge exception" in result.reason
    assert runtime.execution.get_positions("BTC/USDT") == []
    assert runtime.judge_breaker.failure_count == 1


def test_runtime_vetoes_when_judge_circuit_is_open():
    bridge = RuntimeBridge()
    cfg = Config(trading=TradingConfig(symbols=["BTC/USDT"], max_data_age_seconds=120), paper_trading=True)
    runtime = RuntimeSupervisor(bridge, cfg, state_db=StateDB(":memory:"), signal_provider=BuyProvider(), judge_client=ApprovingJudge())
    runtime.judge_breaker.failure_threshold = 1
    runtime.judge_breaker.record_failure()
    result = asyncio.run(runtime.scan_once("BTC/USDT"))
    assert result.approved is False
    assert result.reason == "judge circuit open"
    assert runtime.execution.get_positions("BTC/USDT") == []


def test_forex_weekend_guard_blocks_using_tick_server_time():
    from datetime import datetime, timezone
    from core.market_guard import evaluate_weekend_guard, is_forex_symbol
    assert is_forex_symbol("EURUSD")
    assert not is_forex_symbol("BTC/USDT")
    # Friday 21:00 UTC, inside default two-hour cutoff.
    ts = datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc).timestamp()
    decision = evaluate_weekend_guard(server_epoch_s=ts)
    assert decision.allowed is False
    assert "weekend" in decision.reason


def test_runtime_blocks_forex_weekend_and_allows_crypto():
    from datetime import datetime, timezone
    from unittest.mock import patch
    from core.runtime import RuntimeSupervisor
    from core.state_db import StateDB
    from config import Config, TradingConfig

    class ForexBridge(RuntimeBridge):
        def __init__(self):
            super().__init__()
            self.tick.symbol = "EURUSD"
            self.tick.timestamp_ms = int(datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc).timestamp() * 1000)

    forex = ForexBridge()
    cfg = Config(trading=TradingConfig(symbols=["EURUSD"], max_data_age_seconds=10_000_000), paper_trading=True)
    runtime = RuntimeSupervisor(forex, cfg, state_db=StateDB(":memory:"), signal_provider=BuyProvider())
    result = asyncio.run(runtime.scan_once("EURUSD"))
    assert result.approved is False
    assert "weekend" in result.reason
    assert runtime.execution.get_positions("EURUSD") == []

    crypto = RuntimeBridge()
    cfg = Config(trading=TradingConfig(symbols=["BTC/USDT"], max_data_age_seconds=120), paper_trading=True)
    runtime = RuntimeSupervisor(crypto, cfg, state_db=StateDB(":memory:"), signal_provider=BuyProvider())
    result = asyncio.run(runtime.scan_once("BTC/USDT"))
    assert result.approved is True

def test_emergency_stop_blocks_restart():
    bridge = RuntimeBridge()
    cfg = Config(trading=TradingConfig(symbols=["BTC/USDT"], scan_interval=1), paper_trading=True)
    runtime = RuntimeSupervisor(bridge, cfg, state_db=StateDB(":memory:"))
    runtime.emergency_stop("test")
    assert runtime.start() is False
    assert runtime.status()["state"] == "emergency_stopped"
    runtime.reset_emergency_stop()
    assert runtime.status()["state"] == "stopped"
