"""Vilona AI desktop relay client — outbound-only control-plane connection.

The downloadable desktop binary runs this client. It NEVER listens on a port;
it makes outbound HTTPS requests to the central relay server:

  handshake -> poll (commands) -> execute locally via injected callback -> complete
  report    -> push state-change events (position opened/closed, balance, etc.)

No secrets are hardcoded or logged. The device token is read from env
(vilona_RELAY_DEVICE_TOKEN) or a config file, supplied once by `/pair` in the
Telegram bot. Commands are executed through an injected `handle_command`
callback so this module never imports MT5 or builds a second bridge.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

import requests

logger = logging.getLogger("vilona.client")

DEFAULT_POLL_INTERVAL = float(os.getenv("vilona_RELAY_POLL_INTERVAL", "3"))
REQUEST_TIMEOUT = float(os.getenv("vilona_RELAY_TIMEOUT", "10"))
MAX_BACKOFF = float(os.getenv("vilona_RELAY_MAX_BACKOFF", "60"))


class RelayClient:
    def __init__(
        self,
        relay_url: str,
        device_token: str,
        handle_command: Callable[[str, dict], Any],
        get_account_login: Optional[Callable[[], str]] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        if not relay_url:
            raise ValueError("relay_url required")
        if not device_token:
            raise ValueError("device_token required (from /pair)")
        self.relay_url = relay_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {device_token}"}
        self.handle_command = handle_command
        self.get_account_login = get_account_login or (lambda: "")
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._session = requests.Session()
        self._can_trade = False

    # ── HTTP helpers (never log the token) ────────────────────────
    def _post(self, path: str, body: Optional[dict] = None):
        return self._session.post(
            f"{self.relay_url}{path}", json=body or {},
            headers=self._headers, timeout=REQUEST_TIMEOUT,
        )

    def handshake(self) -> bool:
        try:
            r = self._post("/relay/handshake", {"account_login": self.get_account_login()})
            r.raise_for_status()
            data = r.json()
            self._can_trade = bool(data.get("can_trade"))
            logger.info("handshake ok license=%s can_trade=%s", data.get("license"), self._can_trade)
            return True
        except Exception as e:
            logger.warning("handshake failed: %s", e)
            return False

    def report(self, kind: str, data: dict) -> bool:
        """Push a state-change event (EV_ORDER, EV_CLOSED, EV_STATUS, ...)."""
        try:
            r = self._post("/relay/report", {"kind": kind, "data": data})
            return r.ok
        except Exception as e:
            logger.debug("report(%s) failed: %s", kind, e)
            return False

    def _execute(self, cmd: dict) -> tuple[str, Any]:
        op = cmd.get("op", "")
        args = cmd.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                args = {}
        if op == "runtime.start" and not self._can_trade:
            return ("error", {"reason": "unlicensed: cannot start trading"})
        try:
            result = self.handle_command(op, args)
            return ("done", result)
        except Exception as e:
            logger.error("command %s failed: %s", op, e)
            return ("error", {"error": str(e)})

    def _poll_once(self) -> int:
        r = self._post("/relay/poll")
        r.raise_for_status()
        cmds = r.json() or []
        for cmd in cmds:
            cid = cmd.get("id")
            status, result = self._execute(cmd)
            try:
                self._post("/relay/complete",
                           {"command_id": cid, "op": status, "result": result})
            except Exception as e:
                logger.debug("complete %s failed: %s", cid, e)
        return len(cmds)

    def run_forever(self) -> None:
        backoff = self.poll_interval
        while not self._stop.is_set():
            try:
                if not self.handshake():
                    raise ConnectionError("handshake failed")
                n = self._poll_once()
                backoff = self.poll_interval  # reset on success
                if n == 0:
                    self._stop.wait(backoff)
            except Exception as e:
                logger.warning("relay loop error: %s (retry in %.0fs)", e, backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, name="vilona-relay", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    url = os.getenv("vilona_RELAY_URL", "")
    tok = os.getenv("vilona_RELAY_DEVICE_TOKEN", "")

    def _noop(op, args):
        return {"echo": op}

    c = RelayClient(url, tok, _noop)
    c.run_forever()
