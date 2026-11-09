from __future__ import annotations

import pytest

from config import TradingConfig
from agents import MarketSnapshot, Signal, roles_for, ALL_ROLES
from agents.risk_manager import evaluate as risk_evaluate
from agents.trader import parse_signal
from agents.judge import parse_judge
from agents.researcher import parse_research
from trading.bridge_ccxt import Tick, Position, SymbolInfo


class FakeBridge:
    """In-memory stand-in for CCXTBridge. No network."""

    def __init__(self, bid=100.0, ask=100.1):
        self._tick = Tick(symbol="BTC/USDT", bid=bid, ask=ask, timestamp_ms=1700000000000)
        self._info = SymbolInfo(symbol="BTC/USDT", point=0.01, digits=2)
        self.positions = []
        self.pending = []
        self.closed = []
        self.sl_updates = []

    def get_tick(self, symbol):
        return self._tick

    def get_symbol_info(self, symbol):
        return self._info

    def get_positions(self, symbol=None):
        return list(self.positions)

    def get_pending_orders(self, symbol=None, exclude_tickets=None):
        return list(self.pending)

    def modify_position_sltp(self, ticket, symbol, sl=None, tp=None):
        self.sl_updates.append((ticket, sl, tp))
        for p in self.positions:
            if p.ticket == ticket:
                p.sl = sl if sl is not None else p.sl
                p.tp = tp if tp is not None else p.tp
        return True, "ok"

    def close_position(self, ticket, symbol):
        before = len(self.positions)
        self.positions = [p for p in self.positions if p.ticket != ticket]
        return (len(self.positions) < before), "closed" if len(self.positions) < before else "not found"

    def cancel_order(self, ticket, symbol):
        self.pending = [o for o in self.pending if o.ticket != ticket]
        return True, "cancelled"

    def get_candles(self, symbol, timeframe, limit=100):
        rows = []
        price = self._tick.bid
        for i in range(limit):
            rows.append({"time": 1700000000000 + i * 900000, "open": price - 0.2, "high": price + 0.5,
                         "low": price - 0.5, "close": price + (0.05 if i % 2 == 0 else -0.05), "volume": 10.0})
        return rows


def make_snapshot(bid=100.0, ask=100.1):
    candles = [{"time": i, "open": bid, "high": bid + 1, "low": bid - 1, "close": bid, "volume": 5.0} for i in range(30)]
    return MarketSnapshot(
        symbol="BTC/USDT",
        tick_bid=bid,
        tick_ask=ask,
        candles_15m=candles,
        candles_1h=candles,
        spread_pct=(ask - bid) / bid * 100.0,
        atr_15m=abs(ask - bid) * 10,
        news_headlines=[],
    )


def test_break_even_buys_when_trigger_hit():
    from trading.trade_executor_v2 import manage_breakeven
    bridge = FakeBridge(bid=105.0, ask=105.1)
    bridge.positions = [Position(ticket=1, symbol="BTC/USDT", type="buy", price_open=100.0, sl=0.0, tp=110.0, volume=0.1)]
    mtf = {"15m": [{"time": i, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0} for i in range(30)]}
    logs = manage_breakeven(bridge, "BTC/USDT", [1], trigger_atr_mult=1.0, offset_atr_mult=0.5, mtf_data=mtf)
    assert len(bridge.sl_updates) == 1, logs
    ticket, sl, tp = bridge.sl_updates[0]
    assert ticket == 1
    assert sl > 100.0
    assert tp == 110.0


def test_break_even_not_triggered_when_far():
    from trading.trade_executor_v2 import manage_breakeven
    bridge = FakeBridge(bid=100.5, ask=100.6)
    bridge.positions = [Position(ticket=1, symbol="BTC/USDT", type="buy", price_open=100.0, sl=0.0, tp=110.0, volume=0.1)]
    mtf = {"15m": [{"time": i, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0} for i in range(30)]}
    logs = manage_breakeven(bridge, "BTC/USDT", [1], trigger_atr_mult=2.0, offset_atr_mult=0.5, mtf_data=mtf)
    assert bridge.sl_updates == []


def test_trailing_respects_be_fence():
    from trading.trade_executor_v2 import manage_trailing_stop
    bridge = FakeBridge(bid=110.0, ask=110.1)
    bridge.positions = [Position(ticket=1, symbol="BTC/USDT", type="buy", price_open=100.0, sl=99.0, tp=120.0, volume=0.1)]
    mtf = {"15m": [{"time": i, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0} for i in range(30)]}
    logs = manage_trailing_stop(bridge, "BTC/USDT", [1], trailing_atr_mult=1.0, trailing_step_atr_mult=0.5,
                                be_trigger_atr_mult=1.0, mtf_data=mtf)
    assert bridge.sl_updates == []


def test_risk_manager_rejects_tiny_confidence():
    signal = Signal(symbol="BTC/USDT", action="BUY", confidence=0.3, reason="weak")
    snapshot = make_snapshot()
    cfg = TradingConfig()
    verdict = risk_evaluate(signal, snapshot, equity_usd=10000.0, cfg=cfg, daily_pl_usd=0.0, open_positions_count=0)
    assert verdict.approved is False
    assert "confidence" in verdict.reason


def test_risk_manager_rejects_wait():
    signal = Signal(symbol="BTC/USDT", action="WAIT", confidence=0.9, reason="no edge")
    snapshot = make_snapshot()
    cfg = TradingConfig()
    assert risk_evaluate(signal, snapshot, equity_usd=10000.0, cfg=cfg).approved is False


def test_risk_manager_approves_and_computes_lot():
    signal = Signal(symbol="BTC/USDT", action="BUY", confidence=0.9, reason="strong trend up")
    snapshot = make_snapshot(bid=100.0, ask=100.1)
    cfg = TradingConfig()
    verdict = risk_evaluate(signal, snapshot, equity_usd=10000.0, cfg=cfg, daily_pl_usd=0.0, open_positions_count=0)
    assert verdict.approved is True
    assert verdict.lot_size > 0
    assert verdict.sl_price is not None and verdict.sl_price < 100.1
    assert verdict.tp_price is not None and verdict.tp_price > 100.1
    assert verdict.rr_ratio > 0


def test_trader_parser_handles_bad_json():
    sig = parse_signal("not json at all", "BTC/USDT")
    assert sig.action == "WAIT"
    assert sig.symbol == "BTC/USDT"


def test_judge_parser_defaults_veto_on_garbage():
    approved, reason = parse_judge("garbage")
    assert approved is False
    assert reason == "unparseable judge response - veto"


def test_researcher_parser_defaults_unknown():
    data = parse_research("no json here")
    assert data["trend"] == "unknown"


def test_roles_defaults_to_trader_risk():
    assert roles_for([]) == ("trader", "risk_manager")
    assert roles_for(["judge", "researcher"]) == ("researcher", "judge")
    assert roles_for(None) == ("trader", "risk_manager")


def test_all_roles_subset():
    for role, enabled in [("researcher", True), ("trader", True), ("risk_manager", True), ("judge", True)]:
        assert role in roles_for(list(enabled and [role] or [role]))
    assert set(ALL_ROLES) == {"researcher", "trader", "risk_manager", "judge"}
