"""Multi-user registration + session management for Telegram bot.

Each Telegram user must register via /start before using the bot. First
registrant becomes admin automatically and approves subsequent users.
Per-user bridge sessions isolate credentials and runtime state.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / 'telegram_users.db'


@dataclass
class UserSession:
    chat_id: int
    username: str = ''
    first_name: str = ''
    is_admin: bool = False
    approved: bool = False
    registered_at: float = 0.0
    bridge: Any = None
    runtime: Any = None
    exchange_api_key: str = ''
    exchange_api_secret: str = ''
    exchange_name: str = 'binance'
    exchange_sandbox: bool = False


class UserRegistry:
    """SQLite-backed user store + in-memory session cache."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._sessions: dict[int, UserSession] = {}
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS tg_users (
                        chat_id INTEGER PRIMARY KEY,
                        username TEXT DEFAULT '',
                        first_name TEXT DEFAULT '',
                        is_admin INTEGER DEFAULT 0,
                        approved INTEGER DEFAULT 0,
                        registered_at REAL DEFAULT 0,
                        exchange_name TEXT DEFAULT 'binance',
                        exchange_api_key TEXT DEFAULT '',
                        exchange_api_secret TEXT DEFAULT '',
                        exchange_sandbox INTEGER DEFAULT 0
                    );
                """)
                conn.commit()
            finally:
                conn.close()

    def _row_to_session(self, row: sqlite3.Row) -> UserSession:
        return UserSession(
            chat_id=int(row['chat_id']),
            username=row['username'] or '',
            first_name=row['first_name'] or '',
            is_admin=bool(row['is_admin']),
            approved=bool(row['approved']),
            registered_at=float(row['registered_at']),
            exchange_name=row['exchange_name'] or 'binance',
            exchange_api_key=row['exchange_api_key'] or '',
            exchange_api_secret=row['exchange_api_secret'] or '',
            exchange_sandbox=bool(row['exchange_sandbox']),
        )

    def get(self, chat_id: int) -> Optional[UserSession]:
        with self._lock:
            cached = self._sessions.get(chat_id)
            if cached is not None:
                return cached
            conn = self._connect()
            try:
                row = conn.execute(
                    'SELECT * FROM tg_users WHERE chat_id=?', (chat_id,)
                ).fetchone()
                if row is None:
                    return None
                sess = self._row_to_session(row)
                self._sessions[chat_id] = sess
                return sess
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                return int(conn.execute('SELECT COUNT(*) FROM tg_users').fetchone()[0])
            finally:
                conn.close()

    def register(self, chat_id: int, username: str, first_name: str,
                 exchange_name: str = 'binance',
                 exchange_api_key: str = '', exchange_api_secret: str = '',
                 exchange_sandbox: bool = False) -> UserSession:
        """Register a new user. First user auto-approves + becomes admin."""
        with self._lock:
            conn = self._connect()
            try:
                count = int(conn.execute('SELECT COUNT(*) FROM tg_users').fetchone()[0])
                is_first = count == 0
                sess = UserSession(
                    chat_id=chat_id,
                    username=username or '',
                    first_name=first_name or '',
                    is_admin=is_first,
                    approved=is_first,
                    registered_at=time.time(),
                    exchange_name=exchange_name,
                    exchange_api_key=exchange_api_key,
                    exchange_api_secret=exchange_api_secret,
                    exchange_sandbox=exchange_sandbox,
                )
                conn.execute(
                    """INSERT OR REPLACE INTO tg_users
                       (chat_id, username, first_name, is_admin, approved,
                        registered_at, exchange_name, exchange_api_key,
                        exchange_api_secret, exchange_sandbox)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (chat_id, sess.username, sess.first_name,
                     int(sess.is_admin), int(sess.approved), sess.registered_at,
                     sess.exchange_name, sess.exchange_api_key,
                     sess.exchange_api_secret, int(sess.exchange_sandbox)),
                )
                conn.commit()
                self._sessions[chat_id] = sess
                if is_first:
                    logger.info("First user %s (%s) auto-approved as admin",
                                chat_id, username)
                return sess
            finally:
                conn.close()

    def approve(self, chat_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    'UPDATE tg_users SET approved=1 WHERE chat_id=?', (chat_id,)
                )
                conn.commit()
                if cur.rowcount:
                    if chat_id in self._sessions:
                        self._sessions[chat_id].approved = True
                    return True
                return False
            finally:
                conn.close()

    def set_admin(self, chat_id: int, is_admin: bool) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    'UPDATE tg_users SET is_admin=? WHERE chat_id=?',
                    (int(is_admin), chat_id),
                )
                conn.commit()
                if cur.rowcount and chat_id in self._sessions:
                    self._sessions[chat_id].is_admin = is_admin
                return bool(cur.rowcount)
            finally:
                conn.close()

    def list_pending(self) -> list[UserSession]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    'SELECT * FROM tg_users WHERE approved=0 ORDER BY registered_at'
                ).fetchall()
                return [self._row_to_session(r) for r in rows]
            finally:
                conn.close()

    def list_all(self) -> list[UserSession]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    'SELECT * FROM tg_users ORDER BY registered_at'
                ).fetchall()
                return [self._row_to_session(r) for r in rows]
            finally:
                conn.close()

    def remove(self, chat_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute('DELETE FROM tg_users WHERE chat_id=?', (chat_id,))
                conn.commit()
                self._sessions.pop(chat_id, None)
                return bool(cur.rowcount)
            finally:
                conn.close()
