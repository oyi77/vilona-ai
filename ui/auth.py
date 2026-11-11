"""Auth helpers — thin wrapper over UserRegistry.

Backward-compat module-level helpers kept for existing callers
(telegram_controller.py imports is_authorized/is_admin). The registry
singleton is the source of truth.
"""
from __future__ import annotations

from typing import Optional

from ui.user_registry import UserRegistry, UserSession

_registry: Optional[UserRegistry] = None


def get_registry() -> UserRegistry:
    global _registry
    if _registry is None:
        _registry = UserRegistry()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None


def _legacy_chat_ids() -> set[int]:
    from config import get_config
    cfg = get_config()
    return set(cfg.telegram.chat_ids or [])


def is_authorized(chat_id: int) -> bool:
    """True iff user registered+approved OR on legacy config allowlist."""
    user = get_registry().get(chat_id)
    if user is not None and user.approved:
        return True
    return chat_id in _legacy_chat_ids()


def is_admin(chat_id: int) -> bool:
    user = get_registry().get(chat_id)
    if user is not None and user.is_admin and user.approved:
        return True
    return chat_id in _legacy_chat_ids()



def get_session(chat_id: int) -> Optional[UserSession]:
    return get_registry().get(chat_id)
