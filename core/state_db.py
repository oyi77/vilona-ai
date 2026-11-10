"""SQLite persistence layer for Vilona AI v2."""
from __future__ import annotations
import json
import sqlite3
import time
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any

from config import get_config, DatabaseConfig
from trading.bridge_ccxt import Position

class StateDB:
    def __init__(self, path: Optional[str] = None):
        cfg = get_config().database
        self.path = path or cfg.path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._connect()
        self._ensure_tables()

    def _connect(self):
        with self._lock:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys=ON")
            if self.path != ':memory:':
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")

    def _ensure_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER UNIQUE,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    current_sl REAL,
                    current_tp REAL,
                    status TEXT DEFAULT 'open',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER UNIQUE,
                    symbol TEXT NOT NULL,
                    type TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL,
                    sl REAL,
                    tp REAL,
                    status TEXT DEFAULT 'pending',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    sl REAL,
                    tp REAL,
                    profit REAL,
                    commission REAL,
                    swap REAL,
                    strategy TEXT,
                    reason TEXT,
                    opened_at REAL NOT NULL,
                    closed_at REAL,
                    status TEXT DEFAULT 'open'
                );
                CREATE TABLE IF NOT EXISTS daily_pl (
                    date TEXT PRIMARY KEY,
                    pl REAL NOT NULL,
                    wins INTEGER NOT NULL,
                    total_closed INTEGER NOT NULL,
                    equity REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trailing_state (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT,
                    started_at_ms INTEGER NOT NULL DEFAULT 0,
                    started INTEGER NOT NULL DEFAULT 0,
                    last_sl REAL
                );
                CREATE TABLE IF NOT EXISTS runtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    symbol TEXT NOT NULL DEFAULT '',
                    correlation_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_events_created
                    ON runtime_events(created_at DESC);
            """)
            self._conn.commit()

    def save_position(self, pos: Position) -> int:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO positions
                   (ticket, symbol, side, quantity, entry_price, current_sl, current_tp, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                (pos.ticket, pos.symbol, pos.type, pos.volume, pos.price_open, pos.sl, pos.tp, now, now)
            )
            self._conn.commit()
        return pos.ticket

    def update_sltp(self, ticket: int, sl: Optional[float], tp: Optional[float]):
        with self._lock:
            self._conn.execute(
                "UPDATE positions SET current_sl=?, current_tp=?, updated_at=? WHERE ticket=?",
                (sl, tp, time.time(), ticket)
            )
            self._conn.commit()

    def close_position(self, ticket: int):
        with self._lock:
            self._conn.execute(
                "UPDATE positions SET status='closed', updated_at=? WHERE ticket=?",
                (time.time(), ticket)
            )
            self._conn.commit()

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        with self._lock:
            if symbol:
                rows = self._conn.execute(
                    "SELECT * FROM positions WHERE symbol=? AND status='open'", (symbol,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM positions WHERE status='open'"
                ).fetchall()
            return [dict(r) for r in rows]

    def save_trailing_metadata(self, ticket: int, symbol: str, started_at_ms: int):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO trailing_state (ticket, symbol, started_at_ms, started) VALUES (?, ?, ?, 1)",
                (ticket, symbol, started_at_ms),
            )
            self._conn.commit()

    def get_trailing_metadata(self, ticket: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM trailing_state WHERE ticket=?", (ticket,)).fetchone()
            return dict(row) if row else None

    def prune_trailing_metadata(self, keep: set):
        with self._lock:
            if not keep:
                self._conn.execute("DELETE FROM trailing_state")
            else:
                placeholders = ",".join("?" for _ in keep)
                self._conn.execute(f"DELETE FROM trailing_state WHERE ticket NOT IN ({placeholders})", tuple(keep))
            self._conn.commit()

    def save_trade(self, trade: Dict[str, Any]):
        with self._lock:
            self._conn.execute(
                """INSERT INTO trades 
                   (ticket, symbol, side, quantity, entry_price, exit_price, sl, tp, profit, commission, swap, strategy, reason, opened_at, closed_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade.get('ticket'), trade.get('symbol'), trade.get('side'), trade.get('quantity'),
                 trade.get('entry_price'), trade.get('exit_price'), trade.get('sl'), trade.get('tp'),
                 trade.get('profit'), trade.get('commission'), trade.get('swap'),
                 trade.get('strategy'), trade.get('reason'), trade.get('opened_at'),
                 trade.get('closed_at'), trade.get('status', 'closed'))
            )
            self._conn.commit()

    def save_daily_pl(self, date: str, pl: float, wins: int, total: int, equity: float):
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO daily_pl 
                   (date, pl, wins, total_closed, equity, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, pl, wins, total, equity, time.time())
            )
            self._conn.commit()

    def get_daily_pl(self, date: Optional[str] = None) -> List[Dict]:
        with self._lock:
            if date:
                row = self._conn.execute(
                    "SELECT * FROM daily_pl WHERE date=?", (date,)
                ).fetchone()
                return [dict(row)] if row else []
            return [dict(r) for r in self._conn.execute(
                "SELECT * FROM daily_pl ORDER BY date DESC LIMIT 30"
            ).fetchall()]

    def get_setting(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row['value'] if row else None

    def set_setting(self, key: str, value: str):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
            self._conn.commit()

    def record_event(self, event: Any) -> int:
        """Append a runtime event and return its database id."""
        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO runtime_events
                   (kind, symbol, correlation_id, payload, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (event.kind, event.symbol, event.correlation_id, event.json(), event.created_at),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def get_events(self, limit: int = 100, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            if kind:
                rows = self._conn.execute(
                    "SELECT * FROM runtime_events WHERE kind=? ORDER BY created_at DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM runtime_events ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
