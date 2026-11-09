"""
Vilona AI v2 Trade Executor Module

Adapts Vilona AI v1's BE/Trailing/Drift-Cancellation logic to CCXT bridge.
Maintains identical risk-management behavior; swap out mt5_module for bridge_ccxt.Bridge.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
import time
import asyncio
import logging
from datetime import datetime, timezone

from config import get_config, TradingConfig
from trading.bridge_ccxt import CCXTBridge, Tick, Position, Order, SymbolInfo

logger = logging.getLogger(__name__)


def _atr(mtf_data: Dict[str, List[Dict]], symbol: str, timeframe: str) -> float:
    rates = mtf_data.get(timeframe) or []
    if len(rates) < 20:
        return 0.0
    closes = [r['close'] for r in rates]
    high_low = [r['high'] - r['low'] for r in rates[-20:]]
    return sum(high_low) / len(high_low)


def _round_price(price: float, digits: int) -> float:
    return round(price, digits)


def manage_breakeven(
    bridge: CCXTBridge,
    symbol: str,
    tickets: List[int],
    trigger_atr_mult: float,
    offset_atr_mult: float,
    mtf_data: Optional[Dict[str, List[Dict]]] = None,
) -> List[str]:
    """
    Move SL to break-even when price reaches trigger.
    Logic ported 1:1 from Vilona AI v1 manage_breakeven().
    """
    logs = []
    if trigger_atr_mult <= 0 or not tickets:
        return logs

    info = bridge.get_symbol_info(symbol)
    tick = bridge.get_tick(symbol)
    if not info or not tick:
        return logs

    point = info.point
    digits = info.digits
    atr = _atr(mtf_data or {}, symbol, '15m') if mtf_data else 0.0

    positions = bridge.get_positions(symbol)
    active = [p for p in positions if p.ticket in tickets]

    for position in active:
        open_price = position.price_open
        cur_sl = position.sl
        cur_tp = position.tp

        if position.type == 'buy':
            trigger = open_price + trigger_atr_mult * atr
            new_sl = _round_price(open_price + offset_atr_mult * atr, digits)
            if tick.bid >= trigger and (cur_sl == 0 or new_sl > cur_sl):
                ok, msg = bridge.modify_position_sltp(position.ticket, symbol, sl=new_sl, tp=cur_tp)
                if ok:
                    logs.append(f"BE applied: ticket={position.ticket}, sl={new_sl}")
        elif position.type == 'sell':
            trigger = open_price - trigger_atr_mult * atr
            new_sl = _round_price(open_price - offset_atr_mult * atr, digits)
            if tick.ask <= trigger and (cur_sl == 0 or new_sl < cur_sl):
                ok, msg = bridge.modify_position_sltp(position.ticket, symbol, sl=new_sl, tp=cur_tp)
                if ok:
                    logs.append(f"BE applied: ticket={position.ticket}, sl={new_sl}")

    return logs


def manage_trailing_stop(
    bridge: CCXTBridge,
    symbol: str,
    tickets: List[int],
    trailing_atr_mult: float,
    trailing_step_atr_mult: float,
    be_trigger_atr_mult: float,
    mtf_data: Optional[Dict[str, List[Dict]]] = None,
) -> List[str]:
    """
    Trailing-stop variant limited to given tickets.
    Follows BE-then-trailing pattern: skip trailing if BE not yet triggered.
    """
    logs = []
    if trailing_atr_mult <= 0 or not tickets:
        return logs

    info = bridge.get_symbol_info(symbol)
    tick = bridge.get_tick(symbol)
    if not info or not tick:
        return logs

    point = info.point
    digits = info.digits
    atr = _atr(mtf_data or {}, symbol, '15m') if mtf_data else 0.0
    step = trailing_atr_mult * atr

    positions = bridge.get_positions(symbol)
    active = [p for p in positions if p.ticket in tickets]

    for position in active:
        cur_sl = position.sl
        cur_tp = position.tp

        if position.type == 'buy':
            if be_trigger_atr_mult > 0:
                if cur_sl == 0:
                    continue
                if cur_sl < position.price_open:
                    continue
            new_sl = _round_price(tick.bid - step, digits)
            if new_sl > cur_sl and new_sl > position.price_open:
                ok, msg = bridge.modify_position_sltp(position.ticket, symbol, sl=new_sl, tp=cur_tp)
                if ok:
                    logs.append(f"Trailing applied: ticket={position.ticket}, sl={new_sl}")

        elif position.type == 'sell':
            if be_trigger_atr_mult > 0:
                if cur_sl == 0:
                    continue
                if cur_sl > position.price_open:
                    continue
            new_sl = _round_price(tick.ask + step, digits)
            if (cur_sl == 0 or new_sl < cur_sl) and new_sl < position.price_open:
                ok, msg = bridge.modify_position_sltp(position.ticket, symbol, sl=new_sl, tp=cur_tp)
                if ok:
                    logs.append(f"Trailing applied: ticket={position.ticket}, sl={new_sl}")

    return logs


def close_all_tickets(bridge: CCXTBridge, symbol: str, tickets: List[int]) -> List[str]:
    logs = []
    closed = 0
    positions = bridge.get_positions(symbol)
    target = [p for p in positions if p.ticket in tickets]

    for pos in target:
        ok, msg = bridge.close_position(pos.ticket, symbol)
        if ok:
            closed += 1
            logs.append(f"Closed ticket={pos.ticket}")
        else:
            logs.append(f"Failed to close ticket={pos.ticket}: {msg}")

    return logs


def cancel_drifted_pending(
    bridge: CCXTBridge,
    symbol: str,
    max_drift_points: int,
    exclude_tickets: Optional[List[int]] = None,
    max_drift_candles: int = 0,
    drift_timeframe: str = '15m',
) -> List[str]:
    logs = []
    if max_drift_points <= 0 and max_drift_candles <= 0:
        return logs

    info = bridge.get_symbol_info(symbol)
    tick = bridge.get_tick(symbol)
    if not info or not tick:
        return logs

    point = info.point
    orders = bridge.get_pending_orders(symbol, exclude_tickets=exclude_tickets or [])
    if not orders:
        return logs

    nth_open_ms = None
    if max_drift_candles > 0:
        rates = bridge.get_candles(symbol, drift_timeframe, limit=max_drift_candles)
        if rates and len(rates) >= max_drift_candles:
            nth_open_ms = rates[-1]['time'] * 1000

    for order in orders:
        is_buy_side = order.type in ('buy_stop', 'buy_limit')
        current_price = tick.ask if is_buy_side else tick.bid
        drift_pts = abs(current_price - order.price_open) / point if point else 0.0

        by_pts = max_drift_points > 0 and drift_pts >= max_drift_points
        by_age = nth_open_ms is not None and nth_open_ms > order.time_setup

        if by_pts or by_age:
            ok, msg = bridge.cancel_order(order.ticket, order.symbol)
            reason = "drift" if by_pts else "candle_age"
            logs.append(f"Cancelled {reason}: ticket={order.ticket}, drift={drift_pts:.0f}pts")

    return logs


def calc_daily_pl(bridge: CCXTBridge, symbol: str) -> Tuple[float, int, int]:
    return bridge.calculate_daily_pl(symbol)


def get_closed_deals_today(bridge: CCXTBridge, symbol: str) -> List[Tuple[int, float, int]]:
    return []
