from __future__ import annotations

import threading
import pytest

from config import TradingConfig
from agents import MarketSnapshot, Signal
from agents.risk_manager import evaluate as risk_evaluate
from trading.bridge_ccxt import Tick, Position, SymbolInfo, Order
from core.state_db import StateDB
from trading.trade_executor_v2 import manage_breakeven, manage_trailing_stop, cancel_drifted_pending


class FakeIntegrationBridge:
    """In-memory stand-in for CCXTBridge for integration testing without external dependencies."""

    def __init__(self, bid=100.0, ask=100.1):
        self._tick = Tick(symbol="BTC/USDT", bid=bid, ask=ask, timestamp_ms=1700000000000)
        self._info = SymbolInfo(symbol="BTC/USDT", point=0.01, digits=2, lot_step=0.01, lot_min=0.001, lot_max=100.0)
        self.positions: list[Position] = []
        self.pending: list[Order] = []
        self.cancelled_tickets: list[int] = []
        self.sl_updates: list[tuple[int, float, float]] = []

    def set_bid_ask(self, bid: float, ask: float):
        self._tick.bid = bid
        self._tick.ask = ask

    def get_tick(self, symbol: str) -> Tick:
        return self._tick

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        return self._info

    def get_positions(self, symbol: str | None = None) -> list[Position]:
        return list(self.positions)

    def get_pending_orders(self, symbol: str | None = None, exclude_tickets: list[int] | None = None) -> list[Order]:
        if exclude_tickets:
            return [o for o in self.pending if o.ticket not in exclude_tickets]
        return list(self.pending)

    def modify_position_sltp(self, ticket: int, symbol: str, sl: float | None = None, tp: float | None = None):
        self.sl_updates.append((ticket, sl, tp))
        for p in self.positions:
            if p.ticket == ticket:
                if sl is not None:
                    p.sl = sl
                if tp is not None:
                    p.tp = tp
        return True, "ok"

    def cancel_order(self, ticket: int, symbol: str):
        self.cancelled_tickets.append(ticket)
        self.pending = [o for o in self.pending if o.ticket != ticket]
        return True, "cancelled"

    def get_candles(self, symbol: str, timeframe: str, limit: int = 100):
        rows = []
        price = self._tick.bid
        for i in range(limit):
            rows.append({
                "time": 1700000000000 + i * 900000,
                "open": price - 0.2,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + (0.05 if i % 2 == 0 else -0.05),
                "volume": 10.0
            })
        return rows


def test_be_then_trailing_full_cycle():
    """Test full cycle: move to Break-Even on first move, then trail stop up on subsequent move."""
    bridge = FakeIntegrationBridge(bid=105.0, ask=105.1)
    bridge.positions = [
        Position(ticket=1, symbol="BTC/USDT", type="buy", price_open=100.0, sl=0.0, tp=120.0, volume=0.1)
    ]
    mtf = {
        "15m": [{"time": i, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0} for i in range(30)]
    }

    # Step 1: BE trigger check (bid=105, entry=100, trigger=1.0*atr, offset=0.5*atr)
    logs_be = manage_breakeven(bridge, "BTC/USDT", [1], trigger_atr_mult=1.0, offset_atr_mult=0.5, mtf_data=mtf)
    assert len(bridge.sl_updates) == 1, f"Expected 1 BE update, got {logs_be}"
    ticket, sl1, tp1 = bridge.sl_updates[0]
    assert ticket == 1
    assert sl1 > 100.0, f"Expected SL moved past entry, got {sl1}"

    # Step 2: Price continues upward to bid=115, call manage_trailing_stop
    bridge.set_bid_ask(115.0, 115.1)
    logs_trail = manage_trailing_stop(
        bridge, "BTC/USDT", [1],
        trailing_atr_mult=1.0, trailing_step_atr_mult=0.5,
        be_trigger_atr_mult=1.0, mtf_data=mtf
    )
    assert len(bridge.sl_updates) == 2, f"Expected 2 total SL updates, got {logs_trail}"
    ticket, sl2, tp2 = bridge.sl_updates[1]
    assert ticket == 1
    assert sl2 > sl1, f"Expected SL moved up from {sl1} to {sl2}"


def test_db_roundtrip_position():
    """Test full CRUD lifecycle of a position in StateDB."""
    db = StateDB(':memory:')
    pos = Position(
        ticket=101,
        symbol="BTC/USDT",
        type="buy",
        price_open=50000.0,
        sl=49000.0,
        tp=52000.0,
        volume=0.5
    )

    # 1. Save position
    t = db.save_position(pos)
    assert t == 101
    positions = db.get_positions()
    assert len(positions) == 1
    assert positions[0]['ticket'] == 101
    assert positions[0]['entry_price'] == 50000.0
    assert positions[0]['current_sl'] == 49000.0
    assert positions[0]['current_tp'] == 52000.0
    assert positions[0]['status'] == 'open'

    # 2. Update SL/TP
    db.update_sltp(101, sl=49500.0, tp=53000.0)
    positions_after_update = db.get_positions()
    assert len(positions_after_update) == 1
    assert positions_after_update[0]['current_sl'] == 49500.0
    assert positions_after_update[0]['current_tp'] == 53000.0

    # 3. Close position
    db.close_position(101)
    positions_after_close = db.get_positions()
    assert len(positions_after_close) == 0


def test_drift_cancel():
    """Test drift cancellation with and without exclusion."""
    bridge = FakeIntegrationBridge(bid=100.0, ask=100.1)
    # Order placed far away at price_open=80.0 -> drift of 20 units = 2000 points
    bridge.pending = [
        Order(ticket=99, symbol="BTC/USDT", type="buy_limit", price_open=80.0, volume=0.1)
    ]

    # With ticket excluded: should NOT cancel
    logs_excluded = cancel_drifted_pending(
        bridge, "BTC/USDT", max_drift_points=50,
        exclude_tickets=[99], max_drift_candles=0
    )
    assert 99 not in bridge.cancelled_tickets
    assert len(bridge.pending) == 1

    # Without exclude: should cancel drifted pending order
    logs_cancelled = cancel_drifted_pending(
        bridge, "BTC/USDT", max_drift_points=50,
        exclude_tickets=[], max_drift_candles=0
    )
    assert 99 in bridge.cancelled_tickets
    assert len(bridge.pending) == 0

def test_thread_safety_db():
    """Test concurrent thread safety when writing trailing metadata."""
    db = StateDB(':memory:')
    num_threads = 10
    barrier = threading.Barrier(num_threads)

    def worker(ticket_id: int):
        barrier.wait()
        db.save_trailing_metadata(ticket=ticket_id, symbol="BTC/USDT", started_at_ms=1700000000000 + ticket_id)

    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(1000 + i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify all 10 rows present
    with db._lock:
        rows = db._conn.execute("SELECT ticket FROM trailing_state").fetchall()
    assert len(rows) == num_threads
    ticket_ids = {r[0] for r in rows}
    expected_ids = {1000 + i for i in range(num_threads)}
    assert ticket_ids == expected_ids


def test_risk_gate_integration():
    """Test risk gate integration for valid high-confidence signals vs rejected low-confidence signals."""
    candles = [
        {"time": i, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 5.0}
        for i in range(30)
    ]
    snapshot = MarketSnapshot(
        symbol="BTC/USDT",
        tick_bid=100.0,
        tick_ask=100.05,
        candles_15m=candles,
        candles_1h=candles,
        spread_pct=0.05,
        atr_15m=2.0,
        news_headlines=[],
    )
    cfg = TradingConfig(max_risk_per_trade_pct=1.0)

    # 1. High confidence signal: should be approved
    good_signal = Signal(symbol="BTC/USDT", action="BUY", confidence=0.9, reason="valid trend")
    verdict_approved = risk_evaluate(good_signal, snapshot, equity_usd=10000.0, cfg=cfg)
    assert verdict_approved.approved is True
    assert verdict_approved.lot_size > 0
    assert verdict_approved.sl_price is not None and verdict_approved.sl_price < 100.05
    assert verdict_approved.tp_price is not None and verdict_approved.tp_price > 100.05

    # 2. Low confidence signal: should be rejected
    weak_signal = Signal(symbol="BTC/USDT", action="BUY", confidence=0.3, reason="weak hint")
    verdict_rejected = risk_evaluate(weak_signal, snapshot, equity_usd=10000.0, cfg=cfg)
    assert verdict_rejected.approved is False
    assert "confidence" in verdict_rejected.reason
