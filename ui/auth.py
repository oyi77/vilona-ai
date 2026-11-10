# Authentication helpers
def is_authorized(chat_id: int) -> bool:
    from config import get_config
    cfg = get_config()
    # An empty allow-list must fail closed, not raise IndexError on startup.
    return chat_id in set(cfg.telegram.chat_ids or [])

def is_admin(chat_id: int) -> bool:
    from config import get_config
    cfg = get_config()
    return chat_id in set(cfg.telegram.admin_chat_ids or [])
