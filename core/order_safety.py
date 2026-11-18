"""Order safety: magic tagging, post-fill SL verification, daily P/L.

Two live defects motivated this module:

1. Every position carried ``magic=0``, so Vilona's trades were
   indistinguishable from manual trades or another EA. Incident triage could
   not tell which positions the bot owned.
2. A position could remain open with ``sl=0.0`` after the EA refused the
   protect call (retcode 10031 "no connection"). An unprotected position is
   unbounded risk and must never survive the attempt.

Rules enforced here:
- An order is never sent without a stop-loss.
- Every order carries a non-zero magic so ownership is provable.
- After the fill, SL is re-applied and verified; if that fails the position is
  closed immediately rather than left naked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional
# Stable base for Vilona-owned magic numbers. Broker-side magic is a ulong, so
# any value in this range is safe and never collides with 0 (manual trades).
MAGIC_BASE = 770000


def resolve_magic(symbol: str, base: int = MAGIC_BASE) -> int:
    """Deterministic non-zero magic for a symbol.

    Deterministic so that reconnecting or restarting never orphans positions:
    the same symbol always yields the same magic, which is what makes
    ``magic`` usable as an ownership filter later.
    """
    if not symbol:
        raise ValueError("symbol is required to resolve a magic number")
    digest = 0
    for char in symbol.upper():
        digest = (digest * 31 + ord(char)) % 1000
    return base + digest


def resolve_min_stop_distance(symbol: str, config: Any = None, default: float = 0.0) -> float:
    """Minimum stop distance the broker will accept for a symbol.

    The demo account publishes no ``stops_level``, so the value has to come from
    configuration. Symbols are matched loosely (``XAUUSD.a`` finds ``XAUUSD``).
    """
    clean = "".join(ch for ch in (symbol or "").upper() if ch.isalnum())
    table: Dict[str, float] = {}
    if config is not None:
        table = getattr(config, "min_stop_distance_by_symbol", None) or {}
    if not table:
        try:
            from config import get_config

            table = getattr(
                get_config().trading, "min_stop_distance_by_symbol", None
            ) or {}
        except Exception:
            table = {}
    for key in sorted(table, key=len, reverse=True):
        if clean.startswith("".join(ch for ch in key.upper() if ch.isalnum())):
            return float(table[key])
    flat = getattr(config, "min_stop_distance", default) if config is not None else default
    return float(flat or default)


@dataclass
class ProtectedOrderResult:
    success: bool
    message: str
    ticket: Optional[int] = None
    sl_verified: bool = False
    closed_after_failure: bool = False


def place_protected_order(
    bridge: Any,
    *,
    symbol: str,
    action: str,
    volume: float,
    sl: Optional[float],
    tp: Optional[float] = None,
    magic: Optional[int] = None,
    comment: str = "vilona-auto",
    reference_price: Optional[float] = None,
    min_stop_distance: float = 0.0,
    digits: Optional[int] = None,
) -> ProtectedOrderResult:
    """Send a market order that is guaranteed to end up protected or closed.

    Steps:
    1. Refuse locally when no SL is supplied — never reach the broker naked.
    2. Send with a non-zero magic so the position is attributable.
    3. Re-apply SL after the fill (some brokers drop SL on market entry) and
       verify that the EA accepted it.
    4. If SL cannot be verified, close the position and fail loudly.
    """
    if sl is None or float(sl) <= 0:
        return ProtectedOrderResult(
            success=False,
            message="refused: order has no stop-loss",
            sl_verified=False,
        )

    sl_value = float(sl)
    tp_value = float(tp) if tp is not None else None
    if digits is not None:
        sl_value = round(sl_value, int(digits))
        if tp_value is not None:
            tp_value = round(tp_value, int(digits))

    # A stop on the wrong side of price never triggers, which is indistinguishable
    # from having no stop at all. Reject before the order reaches the broker.
    if reference_price is not None and float(reference_price) > 0:
        ref = float(reference_price)
        is_buy = str(action).lower().startswith("buy")
        if is_buy and sl_value >= ref:
            return ProtectedOrderResult(
                success=False,
                message=(
                    f"refused: stop-loss {sl_value} is not below entry {ref} for a BUY"
                ),
                sl_verified=False,
            )
        if not is_buy and sl_value <= ref:
            return ProtectedOrderResult(
                success=False,
                message=(
                    f"refused: stop-loss {sl_value} is not above entry {ref} for a SELL"
                ),
                sl_verified=False,
            )
        if min_stop_distance > 0 and abs(ref - sl_value) < float(min_stop_distance):
            return ProtectedOrderResult(
                success=False,
                message=(
                    f"refused: stop distance {abs(ref - sl_value):.5f} is below the "
                    f"broker minimum {float(min_stop_distance):.5f}"
                ),
                sl_verified=False,
            )

    magic_value = resolve_magic(symbol) if magic is None else int(magic)
    if magic_value == 0:
        magic_value = resolve_magic(symbol)

    trade = bridge.send_market_order(
        symbol=symbol,
        action=action,
        volume=volume,
        sl=sl_value,
        tp=tp_value,
        comment=comment,
        magic=magic_value,
    )

    if not trade or not trade.success:
        return ProtectedOrderResult(
            success=False,
            message=getattr(trade, "message", "order rejected"),
        )

    ticket = getattr(trade, "ticket", 0)
    if not ticket:
        return ProtectedOrderResult(
            success=False,
            message="order reported success but returned no ticket",
        )

    # The tolerance is one tick: anything further means the broker holds a stop
    # other than the one risk sizing was computed for. A 2-digit rounding moved
    # a EURUSD stop from 7.5 to 50 pips and still passed an "sl > 0" check.
    tolerance = (10.0 ** -int(digits)) if digits is not None else 1e-5

    def _protected_as_requested() -> bool:
        positions = bridge.get_positions(symbol) or []
        matched = [p for p in positions if p.ticket == ticket]
        if not matched and len(positions) == 1:
            matched = positions
        for p in matched:
            broker_sl = float(getattr(p, "sl", 0.0) or 0.0)
            return broker_sl > 0 and abs(broker_sl - sl_value) <= tolerance * 1.5
        return False

    modify = None

    # The order was sent with its stop already attached, and some EAs refuse a
    # modification on a position that is still fresh. Read the position back
    # first: verifying the stop that is already there is the whole point, and a
    # blind modify can only turn a protected position into a false failure.
    if _protected_as_requested():
        return ProtectedOrderResult(
            success=True,
            message="order placed and protected",
            ticket=ticket,
            sl_verified=True,
        )

    modify = bridge.modify_position_sltp(
        ticket=ticket, symbol=symbol, sl=sl_value, tp=tp_value
    )
    modify_ok = bool(modify and (modify[0] if isinstance(modify, tuple) else getattr(modify, "success", False)))
    modify_message = modify[1] if isinstance(modify, tuple) else getattr(modify, "message", "unknown")

    if modify_ok and _protected_as_requested():
        return ProtectedOrderResult(
            success=True,
            message="order placed and protected",
            ticket=ticket,
            sl_verified=True,
        )

    # The EA refused to protect the position. Leaving it open means unbounded
    # risk, so close it and report the failure instead of pretending it worked.
    close = bridge.close_position(ticket=ticket, symbol=symbol, volume=volume)
    closed = bool(close and (close[0] if isinstance(close, tuple) else getattr(close, "success", False)))
    close_message = close[1] if isinstance(close, tuple) else getattr(close, "message", "unknown")
    return ProtectedOrderResult(
        success=False,
        message=(
            "SL could not be verified "
            f"({modify_message}); "
            + ("position closed" if closed else f"POSITION MAY STILL BE OPEN ({close_message})")
        ),
        ticket=ticket,
        sl_verified=False,
        closed_after_failure=closed,
    )


def compute_daily_pl(deals: Iterable[Dict[str, Any]], since_epoch: int) -> float:
    """Sum realised profit for deals at or after ``since_epoch``.

    The EA does not implement ``calculate_daily_pl``, so the client derives it
    from closed deal history. Only closing deals (``entry == 1``) contribute;
    balance operations and open entries are excluded.
    """
    total = 0.0
    for deal in deals:
        try:
            if int(deal.get("entry", 1)) != 1:
                continue
            if int(deal.get("time", 0)) < since_epoch:
                continue
            total += float(deal.get("profit", 0.0))
        except (TypeError, ValueError):
            continue
    return total
