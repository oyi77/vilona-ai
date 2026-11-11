"""
mt5_detect.py
=============
Deteksi path terminal MetaTrader 5 di Windows (Program Files MT5 + user roaming
instalasi). Return list dict: {'name', 'terminal64', 'portable', 'mt5_data'}.
Dipakai di ui/pages/settings_armada.py LanesSection._add.
"""
import os
import re
from pathlib import Path
import winreg

_APPDATA_ROAMING = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming')
_ORIGIN_PREFIX = 'origin.txt'

def _read_origin(mt5_data: Path) -> str:
    origin_file = mt5_data / _ORIGIN_PREFIX
    try:
        return origin_file.read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def _terminal_from_data(mt5_data: Path) -> Path | None:
    terminal = mt5_data.parent / 'terminal64.exe'
    if terminal.exists():
        return terminal
    origin = _read_origin(mt5_data)
    if origin:
        candidate = Path(origin).parent / 'terminal64.exe'
        if candidate.exists():
            return candidate
    return None


def _scan_roaming() -> list[dict]:
    found: list[dict] = []
    roaming = _APPDATA_ROAMING / 'MetaQuotes' / 'Terminal'
    if not roaming.exists():
        return found
    for mt5_data in roaming.iterdir():
        if not mt5_data.is_dir() or not re.fullmatch(r'[0-9A-F]{32}', mt5_data.name):
            continue
        terminal = _terminal_from_data(mt5_data)
        if terminal is None:
            continue
        found.append({
            'name': mt5_data.name,
            'terminal64': str(terminal),
            'portable': False,
            'mt5_data': str(mt5_data),
        })
    return found


def _scan_program_files() -> list[dict]:
    found: list[dict] = []
    roots = [Path('C:/Program Files'), Path('C:/Program Files (x86)')]
    for root in roots:
        mt5_dir = root / 'MetaTrader 5'
        terminal = mt5_dir / 'terminal64.exe'
        if terminal.exists():
            found.append({
                'name': 'MetaTrader 5 (Program Files)',
                'terminal64': str(terminal),
                'portable': False,
                'mt5_data': str(mt5_dir),
            })
    return found


def detect_terminals() -> list[dict]:
    """Kembalikan semua instalasi MetaTrader 5 yang terdeteksi di PC ini."""
    try:
        roaming = _scan_roaming()
    except Exception:
        roaming = []
    try:
        pf = _scan_program_files()
    except Exception:
        pf = []
    seen: set[str] = set()
    out: list[dict] = []
    for item in roaming + pf:
        key = item['terminal64']
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
