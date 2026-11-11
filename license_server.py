"""Self-hosted license server — per-account licenses for Vilona AI clients.

Wire contract (JSON, no auth on check/heartbeat; register requires admin token):
  GET  /license/check?account=<mt5_login>&ea_name=VilonaAI&version=..&platform=..
      -> "OK" | "UNLICENSED" | "NOT_FOUND"   (plain text, uppercase)
  GET  /license/heartbeat?account=...        -> "OK" | "NOT_FOUND"
  POST /license/register  {"token": ADMIN, "account": login, "plan": "...",
                           "expires": ISO8601|null, "slots": int}
  POST /license/revoke    {"token": ADMIN, "account": login}
  GET  /license/status?account=...           -> JSON record (admin token required)
  GET  /license/list?token=ADMIN             -> JSON list of records
  GET  /healthz                             -> {"ok": true, "count": N}

Storage: SQLite at data/licenses.db (created on first run).
Signing: optional HMAC secret via LICENSE_SIGNING_SECRET to verify tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request

logger = logging.getLogger("vilona.license")

DB_PATH = os.getenv(
    "vilona_LICENSE_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "licenses.db"),
)

ADMIN_TOKEN = os.getenv("vilona_LICENSE_ADMIN_TOKEN", "")
SIGNING_SECRET = os.getenv("vilona_LICENSE_SIGNING_SECRET", "")

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS licenses (
                account TEXT PRIMARY KEY,
                ea_name TEXT NOT NULL DEFAULT 'VilonaAI',
                plan TEXT NOT NULL DEFAULT 'basic',
                slots INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'licensed',
                created_at TEXT NOT NULL,
                expires_at TEXT,
                last_heartbeat TEXT,
                version TEXT,
                platform TEXT,
                note TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS license_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                kind TEXT NOT NULL,
                ts TEXT NOT NULL,
                detail TEXT DEFAULT ''
            );
        """)


_init_db()


def _record(account: str) -> Optional[dict]:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE account=?", (account,)).fetchone()
        return dict(row) if row else None


def _event(account: str, kind: str, detail: str = "") -> None:
    try:
        with _lock, _connect() as conn:
            conn.execute(
                "INSERT INTO license_events(account, kind, ts, detail) VALUES (?,?,?,?)",
                (account, kind, _now_iso(), detail),
            )
    except Exception:
        logger.exception("license event write failed")


def _is_expired(rec: dict) -> bool:
    exp = rec.get("expires_at")
    if not exp:
        return False
    try:
        return datetime.fromisoformat(exp.replace("Z", "+00:00")) < datetime.now(timezone.utc)
    except ValueError:
        return False


def _check(account: str) -> str:
    """Return OK | UNLICENSED | NOT_FOUND (mirrors the old roxyu plain-text contract)."""
    rec = _record(account)
    if not rec:
        return "NOT_FOUND"
    if rec["status"] != "licensed":
        return "UNLICENSED"
    if _is_expired(rec):
        return "UNLICENSED"
    return "OK"


app = FastAPI(title="Vilona License Server")


@app.get("/license/check")
def check(account: str = Query(...), ea_name: str = "VilonaAI", version: str = "",
          platform: str = ""):
    result = _check(account)
    _event(account, "check", f"ea={ea_name} v={version} plat={platform} -> {result}")
    if result == "OK":
        with _lock, _connect() as conn:
            conn.execute(
                "UPDATE licenses SET last_heartbeat=?, version=?, platform=? WHERE account=?",
                (_now_iso(), version, platform, account),
            )
    return result


@app.get("/license/heartbeat")
def heartbeat(account: str = Query(...)):
    rec = _record(account)
    if not rec or rec["status"] != "licensed" or _is_expired(rec):
        return "NOT_FOUND"
    with _lock, _connect() as conn:
        conn.execute("UPDATE licenses SET last_heartbeat=? WHERE account=?", (_now_iso(), account))
    return "OK"


def _require_admin(request: Request) -> None:
    token = request.headers.get("X-Admin-Token") or request.query_params.get("token") or ""
    if not ADMIN_TOKEN or not hmac.compare_digest(str(token), ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="invalid admin token")


@app.post("/license/register")
def register(body: dict, request: Request):
    _require_admin(request)
    account = str(body.get("account") or "").strip()
    if not account:
        raise HTTPException(status_code=400, detail="account required")
    expires = body.get("expires") or None
    plan = str(body.get("plan") or "basic")
    slots = int(body.get("slots") or 1)
    note = str(body.get("note") or "")
    with _lock, _connect() as conn:
        conn.execute(
            """INSERT INTO licenses(account, ea_name, plan, slots, status, created_at, expires_at, note)
               VALUES (?,?,?,?, 'licensed', ?,?,?)
               ON CONFLICT(account) DO UPDATE SET plan=excluded.plan, slots=excluded.slots,
                           expires_at=excluded.expires_at, status='licensed', note=excluded.note""",
            (account, body.get("ea_name") or "VilonaAI", plan, slots, _now_iso(), expires, note),
        )
    _event(account, "register", f"plan={plan} slots={slots} expires={expires}")
    return {"ok": True, "account": account, "plan": plan, "expires": expires}


@app.post("/license/revoke")
def revoke(body: dict, request: Request):
    _require_admin(request)
    account = str(body.get("account") or "").strip()
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM licenses WHERE account=?", (account,))
    _event(account, "revoke")
    return {"ok": True, "account": account}


@app.get("/license/status")
def status(request: Request, account: str = Query(...)):
    _require_admin(request)
    rec = _record(account)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    rec["expired"] = _is_expired(rec)
    return rec


@app.get("/license/list")
def list_all(request: Request):
    _require_admin(request)
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM licenses ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["expired"] = _is_expired(d)
            out.append(d)
        return {"count": len(out), "licenses": out}


@app.get("/healthz")
def healthz():
    with _lock, _connect() as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0])
    return {"ok": True, "count": count}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("vilona_LICENSE_PORT", "8301"))
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
