"""FastAPI webhook receiver for Telegram — serverless-compatible deployment.

Telegram's webhook mode lets the bot scale horizontally behind a load
balancer (each update POSTed to /webhook/{secret} — one worker handles it
and returns 200 immediately). Polling remains the fallback for local dev.

Usage:
    uvicorn serverless:app --host 0.0.0.0 --port 8443
    # then set webhook once (from any machine):
    curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your.host/webhook/<SECRET>"

The shared TelegramController handles message routing + guards, so every
HTTP worker shares the same UserRegistry + runtime state.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response

from config import get_config
from ui.telegram_controller import TelegramController
from core.runtime import RuntimeSupervisor
from core.state_db import StateDB
from trading.bridge_ccxt import CCXTBridge

logger = logging.getLogger(__name__)

app = FastAPI(title="Vilona AI — Telegram webhook", version="2.1")

_webhook_secret: str = os.getenv("vilona_TG_WEBHOOK_SECRET", "")
_tg_controller: Any = None
_runtime: Any = None
_bridge: Any = None


def _build_components() -> tuple[Any, Any, Any]:
    """Build (bridge, runtime, tg_controller) once per worker process."""
    global _bridge, _runtime, _tg_controller
    if _tg_controller is not None:
        return _bridge, _runtime, _tg_controller
    cfg = get_config()
    bridge = CCXTBridge(cfg.exchange)
    bridge.connect()
    _bridge = bridge
    _runtime = RuntimeSupervisor(
        bridge, cfg, state_db=StateDB(), signal_provider=None,
    )
    _tg_controller = TelegramController(bridge, runtime=_runtime)
    logger.info("Serverless components built (bridge=%s runtime=%s)", bridge, _runtime)
    return _bridge, _runtime, _tg_controller


@app.on_event("startup")
async def _startup() -> None:
    _build_components()


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "webhook_configured": bool(_webhook_secret)}


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    if not _webhook_secret or secret != _webhook_secret:
        raise HTTPException(status_code=404)
    _bridge, runtime, tg = _build_components()
    update_dict = await request.json()
    try:
        await tg._app.process_update(update_dict)  # type: ignore[attr-defined]
    except Exception as e:
        logger.exception("webhook update processing failed: %s", e)
    return Response(status_code=200)


def set_webhook(base_url: str, secret: str | None = None) -> str:
    """Register the webhook with Telegram. Returns the response text."""
    import requests
    cfg = get_config()
    token = cfg.telegram.bot_token
    secret = secret or _webhook_secret or os.urandom(16).hex()
    url = f"{base_url.rstrip('/')}/webhook/{secret}"
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": url, "secret_token": secret, "allowed_updates": ["message", "callback_query"]},
        timeout=15,
    )
    return resp.text


def delete_webhook() -> str:
    """Switch back to polling (clears webhook registration)."""
    import requests
    cfg = get_config()
    resp = requests.post(
        f"https://api.telegram.org/bot{cfg.telegram.bot_token}/deleteWebhook",
        timeout=15,
    )
    return resp.text
