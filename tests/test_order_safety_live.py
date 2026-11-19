from __future__ import annotations

import time

from core.order_safety import place_protected_order
from trading.bridge_ccxt import Position, SymbolInfo, Tick
from trading.execution import ExecutionRequest, LiveExecutionAdapter

class RuntimeBridge:
    def __init__(self):
        self.tick = Tick("BTC/USDT", 100.0, 100.1, int(time.time() * 1000))
        self.info = SymbolInfo("BTC/USDT", point=0.01, digits=2)
        self.orders = []


class ProtectedBridge(RuntimeBridge):
    def __init__(self):
        super().__init__()
        self.info = SymbolInfo("BTC/USDT", point=0.01, digits=2)
        self.tick = Tick("BTC/USDT", 100.0, 100.1, int(time.time() * 1000))
        self._positions = []
        self._modified = []
        self._closed = []

    def send_market_order(self, symbol, action, volume, sl=None, tp=None, magic=None):
        ticket = 55
        self._positions = [Position(ticket=ticket, symbol=symbol, type="buy", price_open=100.1, sl=sl or 0.0, tp=tp or 0.0, volume=volume, price_current=100.1, comment="vilona-auto", magic=magic or 0)]
        return True, "placed", ticket

    def get_positions(self, symbol=None):
        return [p for p in self._positions if symbol is None or p.symbol == symbol]

    def modify_position_sltp(self, ticket, symbol, sl=None, tp=None):
        self._modified.append((ticket, symbol, sl, tp))
        for p in self._positions:
            if p.ticket == ticket:
                p.sl = float(sl or 0.0)
                p.tp = float(tp or 0.0)
        return True, "modified"

    def close_position(self, ticket, symbol):
        self._closed.append((ticket, symbol))
        self._positions = [p for p in self._positions if p.ticket != ticket]
        return True, "closed"


class NoSLBridge(ProtectedBridge):
    def send_market_order(self, symbol, action, volume, sl=None, tp=None, magic=None):
        ticket = 55
        self._positions = [Position(ticket=ticket, symbol=symbol, type="buy", price_open=100.1, sl=0.0, tp=0.0, volume=volume, price_current=100.1, comment="vilona-auto", magic=magic or 0)]
        return True, "placed", ticket

    def modify_position_sltp(self, ticket, symbol, sl=None, tp=None):
        self._modified.append((ticket, symbol, sl, tp))
        return False, "modify rejected"


def test_live_adapter_refuses_missing_sl_before_broker_call():
    bridge = ProtectedBridge()
    adapter = LiveExecutionAdapter(bridge)
    result = adapter.submit(ExecutionRequest("BTC/USDT", "BUY", 0.1, sl=None))
    assert result.accepted is False
    assert "stop-loss" in result.message
    assert bridge.orders == []


def test_live_adapter_uses_protected_order_and_verifies_sl():
    bridge = ProtectedBridge()
    adapter = LiveExecutionAdapter(bridge)
    result = adapter.submit(ExecutionRequest("BTC/USDT", "BUY", 0.1, sl=99.0, tp=110.0))
    assert result.accepted is True
    assert result.ticket == "55"
    assert bridge.get_positions("BTC/USDT")[0].sl == 99.0


def test_live_adapter_closes_position_when_sl_not_protected():
    bridge = NoSLBridge()
    adapter = LiveExecutionAdapter(bridge)
    result = adapter.submit(ExecutionRequest("BTC/USDT", "BUY", 0.1, sl=99.0))
    assert result.accepted is False
    assert "SL could not be verified" in result.message
    assert bridge._closed == [(55, "BTC/USDT")]