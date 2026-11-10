from __future__ import annotations

from config import Config, TradingConfig, set_config
from ui.auth import is_admin, is_authorized


def test_empty_telegram_allow_list_fails_closed():
    cfg = Config()
    set_config(cfg)
    assert is_authorized(123) is False
    assert is_admin(123) is False


def test_admins_must_be_authorized_viewers():
    cfg = Config()
    cfg.telegram.chat_ids = [10]
    cfg.telegram.admin_chat_ids = [11]
    assert any("subset" in error for error in cfg.validate())


def test_paper_mode_is_shared_between_config_layers(monkeypatch):
    monkeypatch.setenv("vilona_PAPER_TRADING", "false")
    cfg = Config.from_env()
    assert cfg.paper_trading is False
    assert cfg.trading.paper_trading is False


def test_config_rejects_invalid_scan_interval_and_confidence():
    cfg = Config(trading=TradingConfig(scan_interval=0, min_confidence=1.5))
    errors = cfg.validate()
    assert any("scan_interval" in error for error in errors)
    assert any("min_confidence" in error for error in errors)
