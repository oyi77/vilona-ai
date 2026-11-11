# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\core\\market_cache.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nmarket_cache.py\n===============\nCache lokal kalender ekonomi ForexFactory (data/cache/economic_calendar.json).\n\nDiambil dari QueenAI, dipangkas ke bagian yang dipakai KingAI saja: KingAI\nkhusus autotrade, jadi cache analisa chat, histori chat, dan memory tidak\nikut dibawa. Persistensi: JSON polos + atomic write (tmp + rename).\n"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from config import DATA_DIR, CACHE_DIR
CALENDAR_PATH = CACHE_DIR / 'economic_calendar.json'
CALENDAR_TTL_SECONDS = 43200
def init_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
def clear_all() -> None:
    """Kosongkan data/cache/ (folder sendiri tetap ada)."""
    if not CACHE_DIR.exists():
        return
    else:
        for path in CACHE_DIR.iterdir():
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
def _atomic_write_json(path: Path, data: dict) -> None:
    init_cache_dir()
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp_path.replace(path)
def get_cached_calendar() -> dict | None:
    if not CALENDAR_PATH.exists():
        return
    else:
        try:
            data = json.loads(CALENDAR_PATH.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or 'fetched_at' not in data:
            return None
        else:
            return data
def is_calendar_fresh(cached: dict, max_age_seconds: int=CALENDAR_TTL_SECONDS) -> bool:
    try:
        fetched_at = datetime.fromisoformat(cached['fetched_at'])
    except (KeyError, ValueError, TypeError):
        return False
    return datetime.now(timezone.utc) - fetched_at < timedelta(seconds=max_age_seconds)
def save_calendar(events: list[dict]) -> None:
    _atomic_write_json(CALENDAR_PATH, {'fetched_at': datetime.now(timezone.utc).isoformat(), 'events': events})