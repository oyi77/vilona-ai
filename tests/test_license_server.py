"""Tests for the self-hosted license server (replaces roxyudeveloper.online)."""
import os
import tempfile

import pytest


@pytest.fixture
def lic_app():
    tmp = tempfile.mktemp(suffix=".db")
    os.environ["vilona_LICENSE_ADMIN_TOKEN"] = "admintok"
    os.environ["vilona_LICENSE_DB"] = tmp
    # force fresh module state bound to this DB
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


def _strip(s):
    return s.strip('"')


def test_unknown_account_not_found(lic_app):
    assert _strip(lic_app.get("/license/check", params={"account": "1"}).text) == "NOT_FOUND"


def test_admin_endpoints_require_token(lic_app):
    assert lic_app.post("/license/register", json={"account": "1"}).status_code == 403
    assert lic_app.post("/license/register",
                        headers={"X-Admin-Token": "WRONG"}, json={"account": "1"}).status_code == 403


def test_register_check_heartbeat_revoke(lic_app):
    r = lic_app.post("/license/register", headers={"X-Admin-Token": "admintok"},
                     json={"account": "123456", "plan": "pro", "slots": 4})
    assert r.json()["ok"] is True
    assert _strip(lic_app.get("/license/check", params={"account": "123456"}).text) == "OK"
    assert _strip(lic_app.get("/license/heartbeat", params={"account": "123456"}).text) == "OK"
    lic_app.post("/license/revoke", headers={"X-Admin-Token": "admintok"}, json={"account": "123456"})
    assert _strip(lic_app.get("/license/check", params={"account": "123456"}).text) == "NOT_FOUND"


def test_expired_license_unlicensed(lic_app):
    lic_app.post("/license/register", headers={"X-Admin-Token": "admintok"},
                 json={"account": "999", "expires": "2000-01-01T00:00:00Z"})
    assert _strip(lic_app.get("/license/check", params={"account": "999"}).text) == "UNLICENSED"


def test_list_reflects_state(lic_app):
    lic_app.post("/license/register", headers={"X-Admin-Token": "admintok"}, json={"account": "111"})
    lic_app.post("/license/register", headers={"X-Admin-Token": "admintok"}, json={"account": "222"})
    lst = lic_app.get("/license/list", params={"token": "admintok"}).json()
    assert lst["count"] == 2
    assert {x["account"] for x in lst["licenses"]} == {"111", "222"}
