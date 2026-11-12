"""Vilona AI v2 - MT5 Bridge Module

Bridge to the running MetaTrader 5 terminal on the local machine.
Requires 'MetaTrader5' package and a running MT5 terminal.
"""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from trading.bridge_ccxt import Tick, SymbolInfo, Position, Order


MTF_TIMEFRAMES = {}
if mt5 is not None:
    MTF_TIMEFRAMES = {
        'M1': mt5.TIMEFRAME_M1,
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30,
        'H1': mt5.TIMEFRAME_H1,
        'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1
    }

TYPE_MAP = {}
POSITION_TYPE_MAP = {}
ORDER_TYPE_MAP_REV = {}

if mt5 is not None:
    TYPE_MAP = {
        mt5.ORDER_TYPE_BUY: 'buy',
        mt5.ORDER_TYPE_SELL: 'sell',
        mt5.ORDER_TYPE_BUY_LIMIT: 'buy_limit',
        mt5.ORDER_TYPE_SELL_LIMIT: 'sell_limit',
        mt5.ORDER_TYPE_BUY_STOP: 'buy_stop',
        mt5.ORDER_TYPE_SELL_STOP: 'sell_stop',
    }

    POSITION_TYPE_MAP = {
        mt5.POSITION_TYPE_BUY: 'buy',
        mt5.POSITION_TYPE_SELL: 'sell',
    }

    ORDER_TYPE_MAP_REV = {
        'buy': mt5.ORDER_TYPE_BUY,
        'sell': mt5.ORDER_TYPE_SELL,
        'buy_limit': mt5.ORDER_TYPE_BUY_LIMIT,
        'sell_limit': mt5.ORDER_TYPE_SELL_LIMIT,
        'buy_stop': mt5.ORDER_TYPE_BUY_STOP,
        'sell_stop': mt5.ORDER_TYPE_SELL_STOP,
    }


class MT5Bridge:
    """Wrapper around the official MetaTrader5 package."""

    def __init__(self):
        self._connected = False
        self._symbol_info_cache: Dict[str, SymbolInfo] = {}

    def connect(self, path=None) -> Tuple[bool, str]:
        """Initialize connection to running MT5 terminal."""
        if mt5 is None:
            return (False, "MetaTrader5 package not installed")
        ok = mt5.initialize(path) if path else mt5.initialize()
        if not ok:
            code, desc = mt5.last_error()
            return (False, f"MT5 Connect Fail: {code} {desc}")

        self._connected = True
        info = mt5.terminal_info()
        acc = mt5.account_info()
        acc_txt = f"Login: {acc.login} Server: {acc.server}" if acc else ''
        return (True, f"MT5 Connected: {info.name} {acc_txt}")

    def terminal_exe_path(self) -> str:
        if not self._connected:
            return ''
        info = mt5.terminal_info()
        if info and getattr(info, 'path', ''):
            return str(Path(info.path) / 'terminal64.exe')
        return ''

    def disconnect(self):
        if self._connected:
            mt5.shutdown()
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def check_alive(self) -> bool:
        if not self._connected:
            return False
        if mt5.terminal_info() is None or mt5.account_info() is None:
            self._connected = False
        return self._connected

    def account_label(self) -> str:
        acc = mt5.account_info() if self._connected else None
        return str(acc.login) if acc else ''

    def get_balance(self) -> Dict[str, float]:
        """Return account fields used by the UI without leaking MT5 objects."""
        acc = mt5.account_info() if self._connected else None
        if not acc:
            return {"balance": 0.0, "equity": 0.0, "margin": 0.0, "free_margin": 0.0, "total": 0.0, "free": 0.0}
        balance = float(acc.balance)
        equity = float(acc.equity)
        free_margin = float(acc.margin_free)
        return {
            "balance": balance,
            "equity": equity,
            "margin": float(acc.margin),
            "free_margin": free_margin,
            # Common aliases used by exchange-oriented UI code.
            "total": equity,
            "free": free_margin,
        }

    # --- Symbol Info ---
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]

        if not self._connected:
            return None

        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        sym = SymbolInfo(
            symbol=symbol,
            point=info.point,
            digits=info.digits,
            lot_step=info.volume_step,
            lot_min=info.volume_min,
            lot_max=info.volume_max,
            position_type_buy="buy",
            position_type_sell="sell",
            order_type_buy_stop="buy_stop",
            order_type_buy_limit="buy_limit",
            order_type_sell_stop="sell_stop",
            order_type_sell_limit="sell_limit",
            deal_entry_out="out"
        )
        self._symbol_info_cache[symbol] = sym
        return sym

    # --- Tick ---
    def get_tick(self, symbol: str) -> Optional[Tick]:
        if not self._connected:
            return None
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return Tick(
            symbol=symbol,
            bid=tick.bid,
            ask=tick.ask,
            timestamp_ms=int(tick.time_msc) if hasattr(tick, 'time_msc') else int(tick.time * 1000),
            open=tick.open if hasattr(tick, 'open') else tick.bid,
            high=tick.high if hasattr(tick, 'high') else tick.bid,
            low=tick.low if hasattr(tick, 'low') else tick.bid,
            volume=tick.volume if hasattr(tick, 'volume') else 0.0
        )

    # --- Positions ---
    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        if not self._connected:
            return []
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return []
        result = []
        for pos in positions:
            p = Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                type=POSITION_TYPE_MAP.get(pos.type, 'buy'),
                volume=pos.volume,
                price_open=pos.price_open,
                sl=pos.sl,
                tp=pos.tp,
                price_current=pos.price_current,
                profit=pos.profit,
                swap=pos.swap,
                magic=pos.magic,
                comment=pos.comment or ''
            )
            result.append(p)
        return result

    # --- Orders (Pending) ---
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        if not self._connected:
            return []
        orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
        if orders is None:
            return []
        result = []
        for ord in orders:
            o = Order(
                ticket=ord.ticket,
                symbol=ord.symbol,
                type=TYPE_MAP.get(ord.type, 'buy'),
                volume=ord.volume_initial,
                price=ord.price_open,
                sl=ord.sl,
                tp=ord.tp,
                time_setup=int(ord.time_setup_msc) if hasattr(ord, 'time_setup_msc') else int(ord.time_setup * 1000)
            )
            result.append(o)
        return result

    # --- Market Order ---
    def send_market_order(self, symbol: str, action: str, volume: float,
                          sl: Optional[float] = None, tp: Optional[float] = None,
                          magic: Optional[int] = None) -> Tuple[bool, str, Optional[int]]:
        if not self._connected:
            return False, "Not connected", None

        if not mt5.symbol_select(symbol, True):
            return False, f"Symbol {symbol} not found/selected", None

        order_type = ORDER_TYPE_MAP_REV.get(action.lower())
        if order_type is None:
            return False, f"Invalid action: {action}", None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, "Failed to get tick", None

        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl if sl else 0.0,
            "tp": tp if tp else 0.0,
            "deviation": 20,
            "magic": magic if magic else 0,
            "comment": "Vilona AI v2",
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.retcode if result else "Unknown"
            desc = mt5.TRADE_RETCODE_DICT.get(err, str(err)) if result else "order_send failed"
            return False, f"Order failed: {desc} ({err})", None

        return True, "Order placed", result.order

    # --- Modify SL/TP ---
    def modify_position_sltp(self, ticket: int, symbol: str,
                             sl: Optional[float] = None, tp: Optional[float] = None) -> Tuple[bool, str]:
        if not self._connected:
            return False, "Not connected"

        pos = mt5.positions_get(ticket=ticket)
        if not pos or len(pos) == 0:
            return False, "Position not found"

        pos = pos[0]
        if pos.symbol != symbol:
            return False, "Symbol mismatch"

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": sl if sl else 0.0,
            "tp": tp if tp else 0.0,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.retcode if result else "Unknown"
            return False, f"Modify failed: {err}"
        return True, "SL/TP modified"

    # --- Close Position ---
    def close_position(self, ticket: int, symbol: str) -> Tuple[bool, str]:
        if not self._connected:
            return False, "Not connected"

        pos = mt5.positions_get(ticket=ticket)
        if not pos or len(pos) == 0:
            return False, "Position not found"

        pos = pos[0]
        if pos.symbol != symbol:
            return False, "Symbol mismatch"

        # Opposite order to close
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": pos.magic,
            "comment": "Vilona AI v2 Close",
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.retcode if result else "Unknown"
            return False, f"Close failed: {err}"
        return True, "Position closed"

    # --- Cancel Pending Order ---
    def cancel_order(self, ticket: int, symbol: str) -> Tuple[bool, str]:
        if not self._connected:
            return False, "Not connected"

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
            "symbol": symbol,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.retcode if result else "Unknown"
            return False, f"Cancel failed: {err}"
        return True, "Order cancelled"

    # --- Daily P/L ---
    def calculate_daily_pl(self, symbol: str) -> Tuple[float, int, int]:
        if not self._connected:
            return 0.0, 0, 0
        today_start = int(time.time()) - 86400
        deals = mt5.history_deals_get(today_start, int(time.time()), group=symbol)
        if deals is None:
            return 0.0, 0, 0
        pl = 0.0
        wins = 0
        total = 0
        for d in deals:
            if d.entry == mt5.DEAL_ENTRY_OUT and d.profit != 0:
                pl += d.profit
                total += 1
                if d.profit > 0:
                    wins += 1
        return pl, wins, total

    # --- Server Time ---
    def get_server_time(self, symbol: str) -> int:
        if not self._connected:
            return int(time.time() * 1000)
        # MT5 doesn't have direct server time; use local time
        return int(time.time() * 1000)

    # --- Candles ---
    def get_candles(self, symbol: str, timeframe: str, count: int = 500, **kwargs) -> Optional[List[Dict]]:
        # runtime.py calls with `limit=`; internal callers use `count=`.
        if 'limit' in kwargs and kwargs['limit'] is not None:
            count = int(kwargs['limit'])
        if not self._connected:
            return None
        # Map runtime names ("15m", "1h") to MT5 enum keys ("M15", "H1").
        tf_key = {'15m': 'M15', '1h': 'H1', '1m': 'M1', '5m': 'M5',
                  '30m': 'M30', '4h': 'H4', '1d': 'D1'}.get(timeframe.lower(), timeframe.upper())
        tf = MTF_TIMEFRAMES.get(tf_key)
        if tf is None:
            return None
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            return None
        return [
            {"time": int(r["time"] * 1000), "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "volume": r["tick_volume"]}
            for r in rates
        ]
