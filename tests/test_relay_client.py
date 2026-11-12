"""Integration test: desktop RelayClient <-> relay server, no network/MT5.

Wires a real RelayClient's callbacks against a live in-process relay (TestClient)
by monkeypatching requests.Session.post to route to the TestClient. Proves the
full phone-home loop: pair -> handshake -> command -> execute -> complete, plus
the unlicensed trade-start gate and event report.
"""
import os
import tempfile

import pytest


@pytest.fixture
def relay_env():
    tmp = tempfile.mktemp(suffix=".db")
    os.environ["vilona_LICENSE_ADMIN_TOKEN"] = "admintok"
    os.environ["vilona_RELAY_BOT_TOKEN"] = "relaybot"
    os.environ["vilona_LICENSE_DB"] = tmp
    import importlib
    import license_server
    importlib.reload(license_server)
    license_server._init_db()
    from fastapi.testclient import TestClient
    yield TestClient(license_server.app)
    try:
        os.unlink(tmp)
    except OSError:
        pass


def _route_via_testclient(monkeypatch, tc):
    """Make requests.Session.post hit the TestClient instead of the network."""
    def fake_post(self, url, json=None, headers=None, timeout=None):
        path = url.split("localhost", 1)[-1] if "localhost" in url else url
        # strip base up to host:port
        from urllib.parse import urlparse
        p = urlparse(url)
        resp = tc.post(p.path, json=json or {}, headers=headers or {})
        class R:
            ok = resp.status_code < 400
            status_code = resp.status_code
            def json(self_inner): return resp.json()
            def raise_for_status(self_inner):
                if not self_inner.ok:
                    raise RuntimeError(f"HTTP {resp.status_code}")
        return R()
    monkeypatch.setattr("requests.Session.post", fake_post)


def test_full_phone_home_roundtrip(relay_env, monkeypatch):
    _route_via_testclient(monkeypatch, relay_env)
    from client.client import RelayClient

    BOT = {"X-Relay-Token": "relaybot"}
    d = relay_env.post("/relay/pair", headers=BOT, json={"chat_id": 100, "name": "pc"}).json()

    seen = {}
    def handle(op, args):
        seen[op] = args
        return {"state": "running"} if op == "status" else {"ok": True}

    rc = RelayClient("http://relay.local", d["token"], handle,
                     get_account_login=lambda: "")
    assert rc.handshake() is True
    assert rc._can_trade is False  # no license yet

    # bot enqueues a status command for chat 100
    relay_env.post("/relay/command", headers=BOT, json={"chat_id": 100, "op": "status", "args": {}})
    n = rc._poll_once()
    assert n == 1 and "status" in seen

    # unlicensed runtime.start is refused locally
    status, result = rc._execute({"id": "x", "op": "runtime.start", "args": {}})
    assert status == "error" and "unlicensed" in result["reason"]

    # report a state-change event
    assert rc.report("EV_ORDER", {"ticket": 1, "symbol": "BTCUSD"}) is True
    evs = relay_env.get("/relay/events/100", headers=BOT).json()["events"]
    assert any(e["kind"] == "EV_ORDER" for e in evs)


def test_licensed_can_trade(relay_env, monkeypatch):
    _route_via_testclient(monkeypatch, relay_env)
    from client.client import RelayClient

    BOT = {"X-Relay-Token": "relaybot"}
    relay_env.post("/license/register", headers={"X-Admin-Token": "admintok"},
                   json={"account": "777111"})
    d = relay_env.post("/relay/pair", headers=BOT, json={"chat_id": 100}).json()
    rc = RelayClient("http://relay.local", d["token"], lambda op, a: {"ok": True},
                     get_account_login=lambda: "777111")
    assert rc.handshake() is True
    assert rc._can_trade is True
    status, _ = rc._execute({"id": "y", "op": "runtime.start", "args": {}})
    assert status == "done"


def test_client_requires_credentials():
    from client.client import RelayClient
    with pytest.raises(ValueError):
        RelayClient("", "tok", lambda o, a: None)
    with pytest.raises(ValueError):
        RelayClient("http://x", "", lambda o, a: None)
