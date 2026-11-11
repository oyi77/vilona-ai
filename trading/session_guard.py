# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\session_guard.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nsession_guard.py\n================\nPemulihan sesi Auto Trade setelah crash / PC mati / proses dibunuh.\n\nPenutupan NORMAL (tombol STOP, tutup jendela) menghentikan Auto Trade dan\nmenghapus status sesi. Kalau aplikasi mati TIDAK normal, posisi & pending\ntetap ada di MT5 (SL/TP di broker), tapi semua yang hanya ada di memori -\nBE/trailing, limit harian, pantauan pending Multi-Level/Setup Harian,\nstrategi per ticket - ikut hilang. Modul ini menyimpan semua itu ke disk\nsupaya saat aplikasi dibuka lagi Auto Trade bisa melanjutkan sesi yang\nsama begitu MT5 + lisensi + endpoint AI siap.\n\nDua file di data/:\n- autotrade_session.json : snapshot sesi berjalan (ditulis ulang atomik\n  tiap ada perubahan, dihapus saat STOP normal). Ada + \"running\" True saat\n  aplikasi dibuka = sesi sebelumnya berhenti tidak normal.\n- trade_ledger.jsonl     : buku catatan per ticket (append-only) - model AI,\n  endpoint, strategi, mode yang membuka posisi itu. Dipakai pemulihan\n  (strategi per ticket) dan Rekap Performa per model (Riwayat Trade).\n  Ticket = position_id MT5 (order pembuka == position_id, lihat\n  trade_executor._order_result).\n\nMurni Python (tanpa Qt/MT5) - logika pemulihan ada di restore_plan().\n"""
import json
import os
from datetime import datetime, timezone
from config import DATA_ROOT, DATA_DIR
SESSION_PATH = DATA_DIR / 'autotrade_session.json'
LEDGER_PATH = DATA_DIR / 'trade_ledger.jsonl'
SESSION_VERSION = 1
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')
def session_path(key: str=''):
    """Satu snapshot per lane (key = id lane); key kosong = file lama."""
    if not key:
        return SESSION_PATH
    else:
        safe = ''.join((ch for ch in key if ch.isalnum() or ch in '-_'))
        return SESSION_PATH.with_name(f'autotrade_session_{safe}.json')
def save_session(state: dict, key: str='') -> None:
    """Tulis atomik (tmp + replace) - crash di tengah tulis tidak boleh\n    meninggalkan file setengah jadi."""
    data = dict(state, version=SESSION_VERSION, running=True, updated_at=now_iso(), pid=os.getpid())
    path = session_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=1), encoding='utf-8')
    tmp.replace(path)
def load_session(key: str='') -> dict | None:
    """Snapshot sesi yang BELUM dihentikan normal, atau None."""
    try:
        data = json.loads(session_path(key).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get('running'):
        return None
    else:
        return data
def clear_session(key: str='') -> None:
    try:
        session_path(key).unlink()
    except FileNotFoundError:
        return None
    except OSError:
        return None
def ledger_record(ticket: int, **fields) -> None:
    """Satu baris per ticket yang berhasil dibuka. Gagal tulis tidak boleh\n    mengganggu eksekusi order (sudah terjadi di broker)."""
    if ticket is None:
        return
    else:
        row = {'ticket': int(ticket), 'opened_at': now_iso()}
        row.update({k: v for k, v in fields.items() if v is not None})
        try:
            LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LEDGER_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        except OSError:
            return None
def load_ledger(account: str | None=None) -> dict:
    """ticket -> baris terakhir untuk ticket itu. Baris rusak dilewati.\n\n    Tiap baris juga tersedia lewat kunci (akun, ticket) karena nomor ticket\n    dari broker berbeda boleh bentrok. `account` diisi: hanya akun itu (baris\n    lama tanpa akun dianggap milik akun \"main\")."""
    out = {}
    try:
        with open(LEDGER_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                    acc = str(row.get('account') or 'main')
                    if account is not None and acc != account:
                        continue
                    ticket = int(row['ticket'])
                    out[ticket] = row
                    out[acc, ticket] = row
                except (ValueError, KeyError, TypeError):
                    continue
    except OSError:
        pass
    return out
def restore_plan(state: dict, position_tickets: set[int], pending_tickets: set[int], closed_today_position_ids: set[int], ledger: dict[int, dict] | None=None, server_day: int | None=None) -> dict:
    """Cocokkan snapshot dengan kondisi MT5 SAAT INI.\n\n    - Pending Multi-Level/Setup Harian yang dipantau hanya dilanjutkan\n      kalau ticket-nya MASIH pending di MT5 (yang sudah tereksekusi jadi\n      posisi ditangani BE/trailing; yang hilang dibatalkan/kedaluwarsa).\n    - Ticket Setup Harian yang tertutup SELAMA aplikasi mati tetap\n      mengunci setup baru hari ini (sama seperti kalau tertutup saat jalan).\n    - Strategi per ticket diambil dari snapshot, dilengkapi buku catatan.\n    """
    # ***<module>.restore_plan: Failure: Compilation Error
    ledger = ledger or {}
    ticket_strategy = {}
    for key, name in (state.get('ticket_strategy') or {}).items():
        try:
            ticket_strategy[int(key)] = str(name or '')
        except (TypeError, ValueError):
            continue
    for ticket in position_tickets | pending_tickets:
        if ticket not in ticket_strategy and ticket in ledger:
                ticket_strategy[ticket] = str(ledger[ticket].get('strategy') or '')
    multi_setups = state.get('multi_setups') or []
    dropped = len(state.get('multi_setups') or []) - len(multi_setups)
    daily_tickets = set()
    for t in state.get('daily_tickets') or []:
        try:
            daily_tickets.add(int(t))
        except (TypeError, ValueError):
            pass
    same_day = server_day is None or state.get('server_day') == server_day
    return same_day and (bool(state.get('daily_setup_blocked')) or True)
    daily_blocked = bool(daily_tickets & closed_today_position_ids)
    positions = list(state.get('positions') or [])
    pendings = list(state.get('pendings') or [])
    signal_id = int(state.get('signal_id') or 0)
    return {'ticket_strategy': ticket_strategy, 'daily_setup_blocked': daily_blocked or bool(state.get('daily_setup_blocked')), 'signal_id': signal_id, 'positions': positions, 'pendings': pendings}