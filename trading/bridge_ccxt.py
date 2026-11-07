"""Vilona AI v2 - CCXT Bridge Module

CCXT integration for multi-exchange support (Binance, Bybit, OKX, etc.)
Preserves the same trading logic (BE, Trailing, Drift Cancellation) from Vilona AI v1.
"""

import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
import ccxt

@dataclass
class Tick:
    symbol: str
    bid: float
    ask: float
    timestamp_ms: int
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0

@dataclass
class SymbolInfo:
    symbol: str
    point: float = 0.0001
    digits: int = 2
    lot_step: float = 0.01
    lot_min: float = 0.001
    lot_max: float = 100.0
    position_type_buy: str = "buy"
    position_type_sell: str = "sell"
    order_type_buy_stop: str = "buy_stop"
    order_type_buy_limit: str = "buy_limit"
    order_type_sell_stop: str = "sell_stop"
    order_type_sell_limit: str = "sell_limit"
    deal_entry_out: str = "out"

@dataclass
class Position:
    ticket: int
    symbol: str
    type: str
    price_open: float
    sl: float = 0.0
    tp: float = 0.0
    volume: float = 0.0
    profit: float = 0.0
    magic: int = 0
    comment: str = ""

@dataclass
class Order:
    ticket: int
    symbol: str
    type: str
    price_open: float
    volume: float = 0.0
    time_setup: int = 0

class CCXTBridge:
    def __init__(self, exchange_config):
        """
        Initialize CCXT bridge.
        """
        self.exchange_config = exchange_config
        self._exchange = None
        self._connected = False
        self._symbol_info_cache: Dict[str, SymbolInfo] = {}
        self._magic_numbers: Dict[str, int] = {}

    def connect(self) -> bool:
        try:
            exchange_class = getattr(ccxt, self.exchange_config.name)

            self._exchange = exchange_class({
                'apiKey': self.exchange_config.api_key,
                'secret': self.exchange_config.api_secret,
                'password': self.exchange_config.password,
                'enableRateLimit': True,
                'rateLimit': self.exchange_config.rate_limit,
                'options': {
                    'defaultType': 'spot',
                }
            })

            if self.exchange_config.sandbox:
                self._exchange.set_sandbox_mode(True)

            self._exchange.fetch_time()
            self._connected = True
            return True

        except Exception as e:
            print(f"[CCXTBridge] Connection failed: {e}")
            return False

    def is_connected(self) -> bool:
        return self._connected and self._exchange is not None

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]

        try:
            if not self._exchange:
                return None

            market = self._exchange.market(symbol)

            info = SymbolInfo(
                symbol=symbol,
                point=market['precision']['price'],
                digits=market['precision']['price'],
                lot_step=market['precision']['amount'],
                lot_min=market['limits']['amount']['min'] or 0.001,
                lot_max=market['limits']['amount']['max'] or 100.0,
            )

            self._symbol_info_cache[symbol] = info
            return info

        except Exception as e:
            print(f"[CCXTBridge] Error fetching symbol info for {symbol}: {e}")
            return None

    def get_tick(self, symbol: str) -> Optional[Tick]:
        try:
            if not self._exchange:
                return None

            ticker = self._exchange.fetch_ticker(symbol)

            return Tick(
                symbol=symbol,
                bid=ticker['bid'],
                ask=ticker['ask'],
                timestamp_ms=ticker['timestamp'],
                open=ticker['open'],
                high=ticker['high'],
                low=ticker['low'],
                volume=ticker['quoteVolume'] or ticker['baseVolume'],
            )

        except Exception as e:
            print(f"[CCXTBridge] Error fetching tick for {symbol}: {e}")
            return None

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        positions = []

        try:
            if not self._exchange:
                return positions

            open_positions = self._exchange.fetch_positions([symbol] if symbol else [])

            for pos in open_positions:
                if pos['contracts'] and pos['contracts'] > 0:
                    positions.append(Position(
                        ticket=int(float(pos['positionId'] or pos.get('id', time.time()))),
                        symbol=pos['symbol'],
                        type="buy" if pos['side'] == 'long' else "sell",
                        price_open=float(pos['entryPrice']),
                        sl=float(pos['stopLoss']) if pos['stopLoss'] else 0.0,
                        tp=float(pos['takeProfit']) if pos['takeProfit'] else 0.0,
                        volume=float(pos['contracts']),
                        profit=float(pos['unrealizedPnl'] or 0),
                    ))

        except Exception as e:
            print(f"[CCXTBridge] Error fetching positions: {e}")

        return positions

    def get_pending_orders(self, symbol: Optional[str] = None, exclude_tickets: Optional[List[int]] = None) -> List[Order]:
        orders = []

        try:
            if not self._exchange:
                return orders

            open_orders = self._exchange.fetch_open_orders([symbol] if symbol else [])

            for order in open_orders:
                if exclude_tickets and int(order['id']) in exclude_tickets:
                    continue

                order_type = order['type']
                if order['side'] == 'buy':
                    if order_type == 'limit':
                        order_type = 'buy_limit'
                    elif order_type == 'stop':
                        order_type = 'buy_stop'
                else:
                    if order_type == 'limit':
                        order_type = 'sell_limit'
                    elif order_type == 'stop':
                        order_type = 'sell_stop'

                orders.append(Order(
                    ticket=int(order['id']),
                    symbol=order['symbol'],
                    type=order_type,
                    price_open=float(order['price']),
                    volume=float(order['remaining'] or order['amount']),
                    time_setup=int(order['datetime'][:19].replace('-', '').replace(':', '').replace('T', '') + '000') if order.get('datetime') else 0,
                ))

        except Exception as e:
            print(f"[CCXTBridge] Error fetching pending orders: {e}")

        return orders

    def get_candles(self, symbol: str, timeframe: str, limit: int = 100) -> Optional[List[Dict]]:
        try:
            if not self._exchange:
                return None

            ohlcv = self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            return [{
                'time': int(c[0] / 1000),
                'open': c[1],
                'high': c[2],
                'low': c[3],
                'close': c[4],
                'volume': c[5],
            } for c in ohlcv]

        except Exception as e:
            print(f"[CCXTBridge] Error fetching candles: {e}")
            return None

    def send_market_order(self, symbol: str, action: str, volume: float,
                         sl: Optional[float] = None, tp: Optional[float] = None,
                         magic: Optional[int] = None) -> Tuple[bool, str, Optional[int]]:
        try:
            if not self._exchange:
                return False, "Not connected", None

            if not self._exchange.markets.get(symbol):
                return False, f"Symbol {symbol} not found", None

            volume = self._normalize_lot(symbol, volume)
            if volume <= 0:
                return False, "Invalid volume", None

            if action in ('buy', 'BUY', 'position_type_buy', 'POSITION_TYPE_BUY'):
                side = 'buy'
                order_type = 'market'
            elif action in ('sell', 'SELL', 'position_type_sell', 'POSITION_TYPE_SELL'):
                side = 'sell'
                order_type = 'market'
            else:
                return False, f"Invalid action: {action}", None

            result = self._exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=volume,
            )

            if not result:
                return False, "Order failed", None

            ticket = int(result.get('id', result.get('orderId', time.time())))

            if sl or tp:
                self._modify_position_sltp(ticket, symbol, sl, tp)

            return True, "Order placed", ticket

        except Exception as e:
            return False, str(e), None

    def modify_position_sltp(self, ticket: int, symbol: str,
                             sl: Optional[float] = None, tp: Optional[float] = None) -> Tuple[bool, str]:
        return self._modify_position_sltp(ticket, symbol, sl, tp)

    def _modify_position_sltp(self, ticket: int, symbol: str,
                               sl: Optional[float] = None, tp: Optional[float] = None) -> Tuple[bool, str]:
        try:
            if not self._exchange:
                return False, "Not connected"

            if hasattr(self._exchange, 'fapiPrivatePostPositionMargin'):
                params = {}
                if sl is not None:
                    params['stopLoss'] = sl
                if tp is not None:
                    params['takeProfit'] = tp
                if params:
                    result = self._exchange.fapiPrivatePostPositionMargin(
                        {'symbol': symbol.replace('/', ''), 'positionSide': 'BOTH', **params}
                    )
                    return True, "Futures SL/TP updated"
                else:
                    return True, "No SL/TP changes"
            else:
                positions = self.get_positions(symbol)
                target_pos = next((p for p in positions if p.ticket == ticket), None)
                if not target_pos:
                    return False, "Position not found"

                ok, msg = self.close_position(ticket, symbol)
                if not ok:
                    return False, f"Failed to close: {msg}"

                side = 'buy' if target_pos.type == 'buy' else 'sell'
                ok, msg, new_ticket = self.send_market_order(
                    symbol, side, target_pos.volume, sl=sl, tp=tp
                )
                if ok:
                    return True, "Spot SL/TP updated via close+reopen"
                else:
                    return False, f"Failed to reopen: {msg}"

        except Exception as e:
            return False, str(e)

    def close_position(self, ticket: int, symbol: str) -> Tuple[bool, str]:
        try:
            if not self._exchange:
                return False, "Not connected"

            positions = self.get_positions()
            target_pos = next((p for p in positions if p.ticket == ticket and p.symbol == symbol), None)

            if not target_pos:
                return False, f"Position {ticket} not found for {symbol}"

            if hasattr(self._exchange, 'cancel_all_orders'):
                result = self._exchange.cancel_all_orders(symbol)
                return True, "Futures position closed"
            elif hasattr(self._exchange, 'private_delete_order'):
                result = self._exchange.private_delete_order(
                    id=str(ticket),
                    symbol=symbol,
                )
                return True, "Spot order cancelled"
            else:
                side = 'sell' if target_pos.type == 'buy' else 'buy'
                result = self._exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side,
                    amount=target_pos.volume,
                )
                if result:
                    return True, "Position closed"
                else:
                    return False, "Close order failed"

        except Exception as e:
            return False, str(e)

    def cancel_order(self, ticket: int, symbol: str) -> Tuple[bool, str]:
        try:
            if not self._exchange:
                return False, "Not connected"

            result = self._exchange.cancel_order(str(ticket), symbol)

            if result:
                return True, "Order cancelled"
            else:
                return False, "Cancel failed"

        except Exception as e:
            return False, str(e)

    def cancel_all_orders(self, symbol: str) -> int:
        try:
            if not self._exchange:
                return 0

            orders = self.get_pending_orders(symbol)
            cancelled = 0

            for order in orders:
                ok, _ = self.cancel_order(order.ticket, order.symbol)
                if ok:
                    cancelled += 1

            return cancelled

        except Exception as e:
            print(f"[CCXTBridge] Error cancelling orders: {e}")
            return 0

    def calculate_daily_pl(self, symbol: str) -> Tuple[float, int, int]:
        try:
            if not self._exchange:
                return 0.0, 0, 0

            now = time.time()
            day_start = int(now // 86400 * 86400)

            deals = []
            try:
                deals = self._exchange.fetch_my_trades(
                    symbol=symbol,
                    since=day_start * 1000,
                    limit=1000
                )
            except Exception:
                pass

            pl = 0.0
            wins = 0
            total_closed = len(deals)

            for d in deals:
                if d.get('status') == 'closed' or d.get('type') == 'out':
                    profit = float(d.get('profit', 0) or 0)
                    commission = float(d.get('fee', {}).get('cost', 0) or 0)
                    pl += profit + commission
                    if profit > 0:
                        wins += 1

            return pl, wins, total_closed

        except Exception as e:
            print(f"[CCXTBridge] Error calculating daily PL: {e}")
            return 0.0, 0, 0

    def get_server_time(self, symbol: str) -> int:
        try:
            if self._exchange:
                server_time = self._exchange.fetch_time()
                return server_time
        except Exception:
            pass
        return int(time.time() * 1000)

    def _normalize_lot(self, symbol: str, lot: float) -> float:
        info = self.get_symbol_info(symbol)
        if not info:
            return lot

        step = info.lot_step
        if step <= 0:
            step = 0.01

        normalized = round(lot / step) * step
        normalized = max(info.lot_min, min(info.lot_max, normalized))
        return round(normalized, 8)

    def _get_magic(self, symbol: str) -> int:
        if symbol not in self._magic_numbers:
            self._magic_numbers[symbol] = hash(symbol) % 10000
        return self._magic_numbers[symbol]


def magic_for(symbol: str) -> int:
    return hash(symbol) % 10000


def is_autotrade_magic(magic: int) -> bool:
    return magic > 0