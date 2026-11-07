from __future__ import annotations
from typing import Optional, Set


def _allowed_chat_ids() -> Set[int]:
    from config import get_config
    cfg = get_config()
    return set(cfg.telegram.chat_ids) | set(cfg.telegram.admin_chat_ids)


def is_authorized(chat_id: int) -> bool:
    allowed = _allowed_chat_ids()
    if not allowed:
        return True
    return chat_id in allowed


def is_admin(chat_id: int) -> bool:
    from config import get_config
    cfg = get_config()
    return chat_id in cfg.telegram.admin_chat_ids