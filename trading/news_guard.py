"""
news_guard.py
=============
News Guard - perlindungan Auto Trade dari volatilitas ekstrem saat rilis
ekonomi besar (NFP, rate decision, CPI, dst). Menghitung zona berdasarkan
jarak waktu ke event, dan menyediakan API guard untuk UI (halaman BERITA)
dan engine (AutoTradeEngine._manage_positions / _scan_loop).
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import DATA_DIR
from trading.economic_calendar import get_calendar_events

SETTINGS_PATH = DATA_DIR / 'news_guard_settings.json'

DEFAULT_SETTINGS = {
    'enabled': True,
    'before': 30,
    'force_close': 5,
    'after': 30,
    'include_medium': False,
    'symbol_only': True,
}

_FF_EVENTS: list[dict] = []


@dataclass
class ZoneStatus:
    zone: str  # 'CLEAR' | 'SOFT_GUARD' | 'FORCE_CLOSE' | 'AFTER_NEWS'
    next_event_label: str = ''


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
    except (OSError, ValueError):
        pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass


def set_ff_events(events: list[dict]) -> None:
    """Dipanggil ui/pages/news.py._on_fetched dengan hasil kalender yang sudah dinormalisasi."""
    global _FF_EVENTS
    _FF_EVENTS = [ev for ev in events if isinstance(ev, dict)]


def _parse_time(raw) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _event_currency(ev: dict) -> str:
    return str(ev.get('currency') or '').upper()


def _event_matches_symbol(ev: dict, symbol: str, symbol_only: bool) -> bool:
    if not symbol_only or not symbol:
        return True
    cur = _event_currency(ev)
    return bool(cur) and cur in str(symbol).upper()


def ff_guard_events(events: list[dict], symbol: str, include_medium: bool, symbol_only: bool) -> list[tuple[datetime, str]]:
    """Daftar (datetime, label) event yang relevan untuk `symbol` - dipakai highlight kalender UI."""
    allowed_impacts = ('high', 'medium') if include_medium else ('high',)
    out = []
    for ev in events or []:
        impact = str(ev.get('impact', '')).lower()
        if impact not in allowed_impacts:
            continue
        if not _event_matches_symbol(ev, symbol, symbol_only):
            continue
        t = _parse_time(ev.get('time'))
        if t is None:
            continue
        label = f'{_event_currency(ev)} {ev.get("title", "")}'.strip()
        out.append((t, label))
    out.sort(key=lambda pair: pair[0])
    return out


def guard_events(mt5, symbol: str, settings: dict | None=None) -> list[dict]:
    """Event guard untuk `symbol` - dipakai UI. Return [] kalau tidak ada data kalender."""
    global _FF_EVENTS
    s = settings or load_settings()
    if not _FF_EVENTS:
        try:
            _FF_EVENTS = get_calendar_events()
        except Exception:
            _FF_EVENTS = []
    return [ev for _t, _label in ff_guard_events(_FF_EVENTS, symbol, s.get('include_medium', False), s.get('symbol_only', True))]


def zone_from_events(events: list[dict], now: datetime, before_min: int, force_close_min: int, after_min: int) -> ZoneStatus:
    """Hitung zona News Guard dari jarak waktu `now` ke event-event terdekat."""
    before = timedelta(minutes=before_min)
    force_close = timedelta(minutes=force_close_min)
    after = timedelta(minutes=after_min)

    for ev in sorted(events, key=lambda e: _parse_time(e.get('time')) or now):
        t = _parse_time(ev.get('time'))
        if t is None:
            continue
        if t - before <= now < t - force_close:
            return ZoneStatus(zone='SOFT_GUARD', next_event_label=_event_currency(ev) + ' ' + str(ev.get('title', '')))
        if t - force_close <= now < t:
            return ZoneStatus(zone='FORCE_CLOSE', next_event_label=_event_currency(ev) + ' ' + str(ev.get('title', '')))
        if t <= now < t + after:
            return ZoneStatus(zone='AFTER_NEWS', next_event_label=_event_currency(ev) + ' ' + str(ev.get('title', '')))
    return ZoneStatus(zone='CLEAR')


def next_event(events: list[dict], now: datetime) -> tuple[datetime, str] | None:
    """Event berikutnya setelah `now` - return (datetime, label) atau None."""
    future = []
    for ev in events or []:
        t = _parse_time(ev.get('time'))
        if t is not None and t > now:
            label = f'{_event_currency(ev)} {ev.get("title", "")}'.strip()
            future.append((t, label))
    if not future:
        return None
    return min(future, key=lambda pair: pair[0])


def get_zone_status(mt5, before_min: int, force_close_min: int, after_min: int | None=None) -> ZoneStatus:
    """API engine: status zona berdasarkan event cache FF yang sudah di-set via set_ff_events()."""
    now = datetime.now(timezone.utc)
    after = after_min if after_min is not None else load_settings().get('after', DEFAULT_SETTINGS['after'])
    return zone_from_events(_FF_EVENTS, now, before_min, force_close_min, after)
