# Authentication helpers
def is_authorized(chat_id: int) -> bool:
    from config import get_config
    cfg = get_config()
    authorized = getattr(cfg.telegram, 'authorized_users', [cfg.telegram.chat_ids[0]]) if cfg.telegram.chat_ids else [cfg.telegram.chat_ids[0]]
    return chat_id in (authorized if isinstance(authorized, list) else [authorized])

def is_admin(chat_id: int) -> bool:
    from config import get_config
    cfg = get_config()
    admins = getattr(cfg.telegram, 'admin_users', cfg.telegram.chat_ids[:1])
    return chat_id in (admins if isinstance(admins, list) else [admins])
