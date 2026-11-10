from __future__ import annotations

import asyncio
from types import SimpleNamespace

from config import Config, set_config
from ui.telegram_controller import TelegramController


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.state = "stopped"

    def status(self):
        return {"state": self.state, "paper": True, "error_count": 0}

    def start(self):
        self.calls.append("start")
        self.state = "running"
        return True

    def stop(self):
        self.calls.append("stop")
        self.state = "stopped"
        return True

    def emergency_stop(self, reason):
        self.calls.append(("emergency_stop", reason))
        self.state = "emergency_stopped"

    def reset_emergency_stop(self):
        self.calls.append("reset_emergency_stop")
        self.state = "stopped"


def make_controller():
    cfg = Config()
    cfg.telegram.chat_ids = [123]
    cfg.telegram.admin_chat_ids = [123]
    set_config(cfg)
    return TelegramController(SimpleNamespace(), runtime=FakeRuntime())


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def test_confirmation_is_chat_bound_single_use_and_expiring():
    controller = make_controller()
    token = controller._create_confirmation(123, "emergency_reset")
    assert controller._consume_confirmation(token, 999, "emergency_reset") is None
    assert controller._consume_confirmation(token, 123, "emergency_reset") == {}
    assert controller._consume_confirmation(token, 123, "emergency_reset") is None

    expired = controller._create_confirmation(123, "close_all")
    controller._pending_confirmations[expired]["expires_at"] = 0
    assert controller._consume_confirmation(expired, 123, "close_all") is None


def test_control_actions_route_to_the_shared_runtime():
    controller = make_controller()
    assert controller._apply_control("start_scan") == "Scanner started."
    assert controller._apply_control("stop_scan") == "Scanner stopped."
    assert controller._apply_control("restart_scan") == "Scanner restarted."
    assert controller.runtime.calls == ["start", "stop", "stop", "start"]


def test_emergency_stop_command_is_immediate_and_admin_only():
    controller = make_controller()
    message = FakeMessage()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message)
    context = SimpleNamespace(args=["operator", "requested"])
    asyncio.run(controller.on_emergency_stop(update, context))
    assert controller.runtime.state == "emergency_stopped"
    assert controller.runtime.calls[-1] == ("emergency_stop", "operator requested")
    assert "EMERGENCY STOP" in message.replies[-1]


def test_non_admin_cannot_control_runtime():
    controller = make_controller()
    message = FakeMessage()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=999), message=message)
    asyncio.run(controller.on_emergency_stop(update, SimpleNamespace(args=[])))
    assert controller.runtime.calls == []
    assert message.replies == ["Admin only"]
