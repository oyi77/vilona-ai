"""Tests for the multi-tenant relay endpoints (devices, commands, events)."""
import os
import tempfile

import pytest


@pytest.fixture
def relay_app():
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


BOT = {"X-Relay-Token": "relaybot"}


def _pair(lic_app, chat_id=100, name="dev"):
    r = lic_app.post("/relay/pair", headers=BOT, json={"chat_id": chat_id, "name": name})
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_pair_requires_bot_token(relay_app):
    assert relay_app.post("/relay/pair", json={"chat_id": 1}).status_code == 403
    assert relay_app.post("/relay/pair", headers={"X-Relay-Token": "WRONG"},
                          json={"chat_id": 1}).status_code == 403


def test_pair_returns_token_once(relay_app):
    d = _pair(relay_app, chat_id=100)
    assert d["token"] and d["device_id"]
    # status endpoint must not leak the token hash or raw token
    st = relay_app.get(f"/relay/status/100", headers=BOT).json()
    assert all("token" not in dev and "token_hash" not in dev for dev in st["devices"])


def test_handshake_updates_license(relay_app):
    relay_app.post("/license/register", headers={"X-Admin-Token": "admintok"},
                   json={"account": "777111"})
    d = _pair(relay_app, chat_id=100)
    r = relay_app.post("/relay/handshake", headers=_bearer(d["token"]),
                       json={"account_login": "777111"})
    assert r.status_code == 200
    body = r.json()
    assert body["license"] == "OK" and body["can_trade"] is True

    # unlicensed login
    r2 = relay_app.post("/relay/handshake", headers=_bearer(d["token"]),
                        json={"account_login": "000"})
    assert r2.json()["license"] == "unlicensed" and r2.json()["can_trade"] is False


def test_command_poll_complete_roundtrip(relay_app):
    d = _pair(relay_app, chat_id=100)
    tok = _bearer(d["token"])
    relay_app.post("/relay/handshake", headers=tok, json={"account_login": ""})

    # bot enqueues
    r = relay_app.post("/relay/command", headers=BOT,
                       json={"chat_id": 100, "op": "status", "args": {}})
    assert r.status_code == 200
    cid = r.json()["command_ids"][0]

    # device polls -> sees the command
    polled = relay_app.post("/relay/poll", headers=tok).json()
    assert len(polled) == 1 and polled[0]["id"] == cid and polled[0]["op"] == "status"

    # device completes
    done = relay_app.post("/relay/complete", headers=tok,
                          json={"command_id": cid, "op": "done", "result": {"state": "idle"}})
    assert done.status_code == 200

    # completing again -> 404 (already done)
    again = relay_app.post("/relay/complete", headers=tok,
                           json={"command_id": cid, "op": "done", "result": {}})
    assert again.status_code == 404


def test_foreign_device_cannot_complete(relay_app):
    d1 = _pair(relay_app, chat_id=100)
    d2 = _pair(relay_app, chat_id=200)
    relay_app.post("/relay/command", headers=BOT,
                   json={"chat_id": 100, "op": "status", "args": {}})
    polled = relay_app.post("/relay/poll", headers=_bearer(d1["token"])).json()
    cid = polled[0]["id"]
    # device 2 tries to complete device 1's command
    r = relay_app.post("/relay/complete", headers=_bearer(d2["token"]),
                       json={"command_id": cid, "op": "done", "result": {}})
    assert r.status_code == 403


def test_tenant_isolation_status_and_poll(relay_app):
    d1 = _pair(relay_app, chat_id=100)
    d2 = _pair(relay_app, chat_id=200)
    relay_app.post("/relay/command", headers=BOT,
                   json={"chat_id": 100, "op": "balance", "args": {}})
    # device 2 (chat 200) polls -> must see nothing from chat 100
    polled = relay_app.post("/relay/poll", headers=_bearer(d2["token"])).json()
    assert polled == []
    # chat 200 status has no devices' commands pending
    st = relay_app.get("/relay/status/200", headers=BOT).json()
    assert st["pending_commands"] == 0


def test_command_op_allowlist(relay_app):
    for bad in ["shell", "exec", "filesystem.read", "open", "close_position"]:
        r = relay_app.post("/relay/command", headers=BOT,
                           json={"chat_id": 100, "op": bad, "args": {}})
        assert r.status_code == 400, f"op {bad} should be rejected"


def test_runtime_start_requires_license(relay_app):
    d = _pair(relay_app, chat_id=100)
    tok = _bearer(d["token"])
    relay_app.post("/relay/handshake", headers=tok, json={"account_login": ""})  # unlicensed
    r = relay_app.post("/relay/command", headers=BOT,
                       json={"chat_id": 100, "op": "runtime.start", "args": {}})
    assert r.status_code == 403


def test_runtime_start_with_license(relay_app):
    relay_app.post("/license/register", headers={"X-Admin-Token": "admintok"},
                   json={"account": "777111"})
    d = _pair(relay_app, chat_id=100)
    tok = _bearer(d["token"])
    relay_app.post("/relay/handshake", headers=tok, json={"account_login": "777111"})
    r = relay_app.post("/relay/command", headers=BOT,
                       json={"chat_id": 100, "op": "runtime.start", "args": {}})
    assert r.status_code == 200


def test_report_event_kind_allowlist(relay_app):
    d = _pair(relay_app, chat_id=100)
    tok = _bearer(d["token"])
    ok = relay_app.post("/relay/report", headers=tok,
                        json={"kind": "EV_STATUS", "data": {"state": "running"}})
    assert ok.status_code == 200
    bad = relay_app.post("/relay/report", headers=tok,
                         json={"kind": "ARBITRARY", "data": {"x": 1}})
    assert bad.status_code == 400


def test_report_payload_size_limit(relay_app):
    d = _pair(relay_app, chat_id=100)
    tok = _bearer(d["token"])
    big = {"data": {"blob": "x" * (64 * 1024 + 10)}, "kind": "EV_STATUS"}
    r = relay_app.post("/relay/report", headers=tok, json=big)
    assert r.status_code == 413


def test_command_without_devices_404(relay_app):
    r = relay_app.post("/relay/command", headers=BOT,
                       json={"chat_id": 999, "op": "status", "args": {}})
    assert r.status_code == 404
