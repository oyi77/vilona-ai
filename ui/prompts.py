# Prompt utilities for Telegram formatting
def escape_md_v2(text: str) -> str:
    import re
    pattern = r'([_*\[\]()~`>#+\-=|{}.!])'
    return re.sub(pattern, r'\\\1', text or "")
