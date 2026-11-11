"""
economic_calendar.py
====================
Kalender ekonomi (NFP, rate decision, CPI, dst) disuntik ke prompt AI supaya
tahu ada event besar sebelum kasih rekomendasi entry - lihat pemakaian di
ui/pages/news.py.

PERINGATAN PENTING: sumber data (`_CALENDAR_URL` di bawah) adalah URL JSON
semi-publik yang dipakai luas oleh proyek open-source trading (pola umum
"ff_calendar_thisweek.json" dari domain distribusi ForexFactory), BUKAN API
resmi ForexFactory - tidak ada jaminan/dokumentasi resmi, bisa berhenti
berfungsi atau berubah format tanpa pemberitahuan kapan saja. Karena itu
SEMUA fungsi publik di modul ini WAJIB fail gracefully (return list/string
kosong atau None sesuai kontrak masing-masing) dan TIDAK PERNAH melempar
exception ke pemanggil.
"""
from datetime import datetime, timezone
import requests
from core import market_cache

_CALENDAR_URL = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'

_IMPACT_MAP = {
    'High': 'HIGH',
    'Medium': 'MEDIUM',
    'Low': 'LOW',
}


def _normalize_event(raw: dict) -> dict:
    """Ubah satu entry JSON FF ke bentuk dipakai KingAI (key: time/title/impact/currency/...)."""
    date_str = str(raw.get('date') or '')
    impact_raw = str(raw.get('impact') or '')
    event_time = None
    if date_str:
        try:
            event_time = datetime.fromisoformat(date_str).astimezone(timezone.utc).isoformat()
        except ValueError:
            event_time = date_str
    return {
        'time': event_time,
        'title': raw.get('title') or raw.get('event') or '',
        'impact': _IMPACT_MAP.get(impact_raw, impact_raw.upper() if impact_raw else ''),
        'currency': raw.get('country') or raw.get('currency') or '',
        'forecast': raw.get('forecast') or '',
        'previous': raw.get('previous') or '',
        'actual': raw.get('actual') or '',
    }


def _fetch(force_refresh: bool = False) -> list[dict]:
    """Ambil events dari cache bila fresh; kalau tidak, fetch dan simpan cache."""
    cached = market_cache.get_cached_calendar()
    if cached is not None and market_cache.is_calendar_fresh(cached) and not force_refresh:
        return [ev for ev in cached.get('events') or [] if isinstance(ev, dict)]
    try:
        resp = requests.get(_CALENDAR_URL, timeout=15.0)
        resp.raise_for_status()
        raw_events = resp.json()
    except Exception:
        return [ev for ev in (cached or {}).get('events') or [] if isinstance(ev, dict)]
    events = [_normalize_event(ev) for ev in raw_events if isinstance(ev, dict)]
    if events:
        market_cache.save_calendar(events)
    return events


def get_calendar_events(force_refresh: bool = False) -> list[dict]:
    """API utama untuk ui/pages/news.py — selalu return list[dict], tidak pernah raise."""
    try:
        return _fetch(force_refresh=force_refresh)
    except Exception:
        return []
