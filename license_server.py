"""Self-hosted license server — per-account licenses for Vilona AI clients.

License wire contract (JSON, no auth on check/heartbeat; register requires admin token):
  GET  /license/check?account=<mt5_login>&ea_name=VilonaAI&version=..&platform=..
      -> "OK" | "UNLICENSED" | "NOT_FOUND"   (plain text, uppercase)
  GET  /license/heartbeat?account=...        -> "OK" | "NOT_FOUND"
  POST /license/register  {"token": ADMIN, "account": login, "plan": "...",
                           "expires": ISO8601|null, "slots": int}
  POST /license/revoke    {"token": ADMIN, "account": login}
  GET  /license/status?account=...           -> JSON record (admin token required)
  GET  /license/list?token=ADMIN             -> JSON list of records
  GET  /healthz                             -> {"ok": true, "count": N}

Multi-tenant relay (one service hosts license + relay):
  Bot API (internal, X-Relay-Token header == vilona_RELAY_BOT_TOKEN, constant-time):
    POST /relay/pair       {chat_id, name}            -> {device_id, token} (token shown ONCE)
    POST /relay/command    {chat_id, op, args}        -> enqueue for active devices of chat
    GET  /relay/status/{chat_id}                      -> own devices + queued counts
    GET  /relay/events/{chat_id}                      -> recent events, chat-scoped
  Device API (Bearer <device token>; only SHA-256 hash stored; never returned):
    POST /relay/handshake  {account_login}            -> license info for the MT5 login
    POST /relay/poll                            -> lease pending commands (<=10, lease TTL)
    POST /relay/complete   {command_id, status, result} -> only for commands leased to this device
    POST /relay/report     {kind, status, data}     -> allowlisted event append, <=64KB

Storage: SQLite at data/licenses.db (created on first run).
Signing: optional HMAC secret via LICENSE_SIGNING_SECRET to verify tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request

logger = logging.getLogger("vilona.license")

DB_PATH = os.getenv(
    "vilona_LICENSE_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "licenses.db"),
)

ADMIN_TOKEN = os.getenv("vilona_LICENSE_ADMIN_TOKEN", "")
SIGNING_SECRET = os.getenv("vilona_LICENSE_SIGNING_SECRET", "")
RELAY_BOT_TOKEN = os.getenv("vilona_RELAY_BOT_TOKEN", "")

LEASE_SECONDS = int(os.getenv("vilona_RELAY_LEASE_SECONDS", "120"))
MAX_BATCH = 10
MAX_EVENT_BYTES = 64 * 1024
ALLOWED_EVENT_KINDS = {"EV_ACCOUNT", "EV_ACCT_STATS", "EV_STATUS", "EV_TICK", "EV_LOG",
                       "EV_STATS", "EV_ORDER", "EV_CLOSED", "EV_GOV", "EV_LICENSE"}
ALLOWED_COMMAND_OPS = {"status", "balance", "positions",
                       "runtime.start", "runtime.stop",
                       "runtime.emergency_stop", "runtime.emergency_reset"}

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
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                name TEXT,
                account_login TEXT,
                license_status TEXT NOT NULL DEFAULT 'unlicensed',
                last_seen TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                revoked TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_devices_chat_id ON devices(chat_id);
            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                op TEXT NOT NULL,
                args JSON NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                lease_until TEXT,
                completed_at TEXT,
                result JSON
            );
            CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
            CREATE INDEX IF NOT EXISTS idx_commands_device_id ON commands(device_id);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                data JSON,
                ts TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_device_id ON events(device_id);
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
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


# ── Auth helpers ──────────────────────────────────────────────────

def _require_bot(request: Request) -> None:
    """X-Relay-Token: internal server-to-server auth (bot or admin UI)."""
    token = request.headers.get("X-Relay-Token") or ""
    if not RELAY_BOT_TOKEN or not hmac.compare_digest(str(token), RELAY_BOT_TOKEN):
        raise HTTPException(status_code=403, detail="invalid relay bot token")


def _device_from_bearer(request: Request) -> dict:
    """Look up a device by Bearer token hash; return dict row."""
    raw = (request.headers.get("Authorization") or "").split(" ", 1)
    if len(raw) != 2:
        raise HTTPException(status_code=401, detail="missing bearer token")
    token_hash = hashlib.sha256(raw[1].encode()).hexdigest()
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM devices WHERE token_hash=? AND revoked IS NULL AND status!='offline'",
            (token_hash,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="invalid or revoked device token")
        return dict(row)


# ── Relay endpoints ───────────────────────────────────────────────

@app.post("/relay/pair")
def pair(body: dict, request: Request):
    _require_bot(request)
    chat_id = int(body.get("chat_id", 0))
    if chat_id <= 0:
        raise HTTPException(status_code=400, detail="valid chat_id required")
    name = str(body.get("name") or "").strip()[:64]
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    device_id = str(uuid.uuid4())
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO devices(device_id, chat_id, token_hash, name, created_at) VALUES (?,?,?,?,?)",
            (device_id, chat_id, token_hash, name, _now_iso()),
        )
    return {"device_id": device_id, "token": raw_token}


@app.post("/relay/handshake")
def handshake(body: dict, request: Request):
    device = _device_from_bearer(request)
    account_login = str(body.get("account_login") or "").strip()
    lic = "unlicensed"
    if account_login:
        lic = _check(account_login)
        if lic != "OK":
            lic = "unlicensed"
    device["account_login"] = account_login or device.get("account_login")
    device["license_status"] = lic
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE devices SET account_login=?, license_status=?, last_seen=? WHERE device_id=?",
            (account_login, lic, _now_iso(), device["device_id"]),
        )
    return {
        "ok": True,
        "device_id": device["device_id"],
        "license": lic,
        "can_trade": lic == "OK",
    }


@app.post("/relay/poll")
def poll(request: Request):
    device = _device_from_bearer(request)
    did = device["device_id"]
    now = _now_iso()
    lease_exp = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()
    # Recover expired leases belonging to THIS device only
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE commands SET status='pending', lease_until=NULL, completed_at=NULL "
            "WHERE status='leased' AND device_id=? AND lease_until<?",
            (did, now),
        )
        # Lease only this device's pending commands (enqueue already targeted device_id)
        conn.execute(
            "UPDATE commands SET status='leased', lease_until=? "
            "WHERE status='pending' AND device_id=? "
            "ORDER BY created_at LIMIT ?",
            (lease_exp, did, MAX_BATCH),
        )
        rows = conn.execute(
            "SELECT * FROM commands WHERE status='leased' AND device_id=? ORDER BY created_at",
            (did,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/relay/complete")
def complete(body: dict, request: Request):
    device = _device_from_bearer(request)
    cid = str(body.get("command_id") or "")
    did = device["device_id"]
    op = str(body.get("op") or "done")
    result = body.get("result")
    if op not in ("done", "error"):
        raise HTTPException(status_code=400, detail="op must be done or error")
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT status, device_id FROM commands WHERE id=? AND (status='leased' OR status='pending')",
            (cid,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="command not found or already done")
        r = dict(row)
        if r["device_id"] != did:
            raise HTTPException(status_code=403, detail="command not leased to this device")
        conn.execute(
            "UPDATE commands SET status=?, completed_at=?, result=? WHERE id=?",
            (op, _now_iso(), json.dumps(result) if result else None, cid),
        )
    return {"ok": True}


@app.post("/relay/report")
def report(body: dict, request: Request):
    device = _device_from_bearer(request)
    did = device["device_id"]
    kind = str(body.get("kind") or "")
    if kind not in ALLOWED_EVENT_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown event kind: {kind}")
    data = body.get("data")
    # Bound payload
    raw = json.dumps(data).encode() if data is not None else b"null"
    if len(raw) > MAX_EVENT_BYTES:
        raise HTTPException(status_code=413, detail="event payload too large (max 64KB)")
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO events(device_id, kind, data, ts) VALUES (?,?,?,?)",
            (did, kind, raw.decode("utf-8", errors="replace"), _now_iso()),
        )
        conn.execute(
            "UPDATE devices SET last_seen=? WHERE device_id=?",
            (_now_iso(), did),
        )
    return {"ok": True}


@app.post("/relay/command")
def relay_command(body: dict, request: Request):
    _require_bot(request)
    chat_id = int(body.get("chat_id", 0))
    if chat_id <= 0:
        raise HTTPException(status_code=400, detail="valid chat_id required")
    op = str(body.get("op") or "")
    if op not in ALLOWED_COMMAND_OPS:
        raise HTTPException(status_code=400, detail=f"unknown command op: {op}")
    args = body.get("args") or {}
    with _lock, _connect() as conn:
        devices = conn.execute(
            "SELECT device_id, license_status FROM devices "
            "WHERE chat_id=? AND revoked IS NULL AND status='active'",
            (chat_id,),
        ).fetchall()
        if not devices:
            raise HTTPException(status_code=404, detail="no active devices for this user")
        # runtime.start blocked for unlicensed
        if op == "runtime.start":
            licensed = [d for d in devices if d["license_status"] == "OK"]
            if not licensed:
                raise HTTPException(
                    status_code=403,
                    detail="no licensed devices available to start trading",
                )
            devices = licensed
        cids = []
        for d in devices:
            cid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO commands(id, device_id, op, args, created_at) VALUES (?,?,?,?,?)",
                (cid, d["device_id"], op, json.dumps(args), _now_iso()),
            )
            cids.append(cid)
    return {"command_ids": cids}


@app.get("/relay/status/{chat_id}")
def relay_status(request: Request, chat_id: int):
    _require_bot(request)
    with _lock, _connect() as conn:
        devs = conn.execute(
            "SELECT device_id, chat_id, name, account_login, license_status, "
            "last_seen, status, revoked FROM devices WHERE chat_id=?",
            (chat_id,),
        ).fetchall()
        pending = int(conn.execute(
            "SELECT COUNT(*) FROM commands c JOIN devices d ON c.device_id=d.device_id "
            "WHERE d.chat_id=? AND c.status IN ('pending','leased')",
            (chat_id,),
        ).fetchone()[0])
    return {
        "chat_id": chat_id,
        "devices": [dict(d) for d in devs],
        "pending_commands": pending,
    }


@app.get("/relay/events/{chat_id}")
def relay_events(request: Request, chat_id: int):
    _require_bot(request)
    limit = int(request.query_params.get("limit", 50))
    if limit < 1 or limit > 200:
        limit = 50
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT e.* FROM events e JOIN devices d ON e.device_id=d.device_id "
            "WHERE d.chat_id=? ORDER BY e.ts DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return {"events": [dict(r) for r in rows]}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("vilona_LICENSE_PORT", "8301"))
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
