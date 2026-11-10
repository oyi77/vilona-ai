"""Execution ports and paper/live adapters.

The runtime talks to this module instead of calling CCXT or MT5 directly. Paper
mode is intentionally deterministic and never invokes a broker order method.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol
import time

from trading.bridge_ccxt import Position


@dataclass(frozen=True)
class ExecutionRequest:
    symbol: str
    action: str
    quantity: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    client_order_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    paper: bool
    symbol: str
    action: str
    quantity: float
    fill_price: Optional[float] = None
    ticket: Optional[str] = None
    message: str = ""
    client_order_id: str = ""


class ExecutionPort(Protocol):
    paper: bool

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]: ...
    def get_equity(self) -> float: ...
    def submit(self, request: ExecutionRequest) -> ExecutionResult: ...
    def close_position(self, ticket: int, symbol: str) -> tuple[bool, str]: ...


class LiveExecutionAdapter:
    paper = False

    def __init__(self, bridge: Any):
        self.bridge = bridge

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        return self.bridge.get_positions(symbol)

    def get_equity(self) -> float:
        balance = self.bridge.get_balance()
        return float(balance.get("equity", balance.get("total", 0.0)) or 0.0)

    def submit(self, request: ExecutionRequest) -> ExecutionResult:
        ok, message, ticket = self.bridge.send_market_order(
            request.symbol, request.action, request.quantity, request.sl, request.tp
        )
        return ExecutionResult(
            accepted=ok,
            paper=False,
            symbol=request.symbol,
            action=request.action,
            quantity=request.quantity,
            ticket=str(ticket) if ticket is not None else None,
            message=message,
            client_order_id=request.client_order_id,
        )

    def close_position(self, ticket: int, symbol: str) -> tuple[bool, str]:
        return self.bridge.close_position(ticket, symbol)


class PaperExecutionAdapter:
    paper = True

    def __init__(self, bridge: Any, starting_equity: Optional[float] = None):
        self.bridge = bridge
        self.equity = float(starting_equity or 10_000.0)
        self._positions: Dict[int, Position] = {}
        self._next_ticket = 1

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        positions = list(self._positions.values())
        return [p for p in positions if symbol is None or p.symbol == symbol]

    def get_equity(self) -> float:
        return self.equity

    def submit(self, request: ExecutionRequest) -> ExecutionResult:
        tick = self.bridge.get_tick(request.symbol)
        if not tick:
            return ExecutionResult(False, True, request.symbol, request.action, request.quantity, message="market data unavailable", client_order_id=request.client_order_id)
        action = request.action.upper()
        if action not in ("BUY", "SELL") or request.quantity <= 0:
            return ExecutionResult(False, True, request.symbol, action, request.quantity, message="invalid paper order", client_order_id=request.client_order_id)
        price = float(tick.ask if action == "BUY" else tick.bid)
        ticket = self._next_ticket
        self._next_ticket += 1
        self._positions[ticket] = Position(
            ticket=ticket,
            symbol=request.symbol,
            type=action.lower(),
            price_open=price,
            sl=float(request.sl or 0.0),
            tp=float(request.tp or 0.0),
            volume=float(request.quantity),
            price_current=price,
            comment="paper",
        )
        return ExecutionResult(True, True, request.symbol, action, request.quantity, price, str(ticket), "paper fill", request.client_order_id)

    def close_position(self, ticket: int, symbol: str) -> tuple[bool, str]:
        position = self._positions.get(ticket)
        if not position or position.symbol != symbol:
            return False, "paper position not found"
        del self._positions[ticket]
        return True, "paper position closed"
