# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\core\\account_license.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Different bytecode
"""\naccount_license.py\n==================\nLisensi KingAI PER AKUN MT5 (bukan per aplikasi).\n\nAplikasi bebas dibuka tanpa aktivasi. Yang dilisensikan adalah ID trading\n(nomor login MT5): worker tiap akun membaca login LANGSUNG dari terminal yang\ntersambung lalu menanyakannya ke server lisensi. Pengguna tidak pernah\nmengetik ID, jadi tidak bisa \"meminjam\" ID berlisensi milik orang lain -\npair di akun tanpa lisensi tidak bisa di-Start. Batas jumlah ID per member\n(mis. 4 ID per member grup) diatur di server lisensi.\n\nPengguna mengisi ID Trading (lisensi) di kartu akun MT5; ID itu wajib sama\ndengan login yang benar-benar aktif di terminal.\n\nStatus:\n    missing     ID Trading akun belum diisi\n    mismatch    ID yang diisi beda dengan login terminal\n    licensed    server menjawab OK (atau masih dalam masa tenggang offline)\n    unlicensed  server menolak ID ini\n    unverified  server tidak terjangkau & tidak ada hasil OK baru-baru ini\n    \"\"          belum dicek (akun belum tersambung)\n\nMasa tenggang: bila server lisensi tidak terjangkau, hasil OK terakhir untuk\nlogin yang sama tetap berlaku GRACE_SECONDS. Catatannya disimpan terenkripsi\nDPAPI (core/secure_store) - menyunting berkasnya tidak menghasilkan lisensi.\n"""
from __future__ import annotations
import json
import time
import threading
from core import secure_store
from core.config import DATA_DIR
from core.i18n import tr
from core.license_client import LICENSE_CONTACT, LicenseClient
LICENSED, UNLICENSED, UNVERIFIED, NONE = ('licensed', 'unlicensed', 'unverified', '')
MISSING, MISMATCH = ('missing', 'mismatch')
GRACE_SECONDS = 259200
RECHECK_MS = 3600000
CACHE_PATH = DATA_DIR / 'license_cache.json'
__all__ = ['LICENSED', 'UNLICENSED', 'UNVERIFIED', 'NONE', 'GRACE_SECONDS', 'RECHECK_MS', 'LICENSE_CONTACT', 'MISSING', 'MISMATCH', 'server_check', 'evaluate', 'empty', 'clean_id', 'valid_id', 'install_gate', 'set_current', 'current', 'block_reason', 'reason_for']
def empty(login: str='', entered: str='') -> dict:
    return {'login': login, 'entered': entered, 'status': NONE, 'grace': False, 'message': '', 'checked_at': 0.0}
def clean_id(raw) -> str:
    return str(raw or '').strip()
def valid_id(raw) -> bool:
    """ID Trading = nomor login MT5: kosong (belum diisi) atau angka saja."""
    text = clean_id(raw)
    return not text or text.isdigit()
_lock = threading.Lock()
_required = False
_current = empty()
def install_gate() -> None:
    global _required
    _required = True
def set_current(lic: dict) -> None:
    global _current
    with _lock:
        _current = dict(lic)
def current() -> dict:
    with _lock:
        return dict(_current)
def block_reason() -> str | None:
    """None bila trading boleh jalan, selain itu pesan siap tampil."""
    if not _required:
        return
    else:
        lic = current()
        return reason_for(lic)
def reason_for(lic: dict) -> str | None:
    """Pesan penolakan untuk satu hasil lisensi (dipakai worker & Hub)."""
    status = lic.get('status')
    if status == LICENSED:
        return
    else:
        login = lic.get('login') or '-'
        if status == MISSING:
            return tr('king.lic_lane_missing')
        else:
            if status == MISMATCH:
                return tr('king.lic_lane_mismatch', id=lic.get('entered') or '-', login=login)
            else:
                if status == UNLICENSED:
                    return tr('king.lic_lane_blocked', login=login, contact=LICENSE_CONTACT)
                else:
                    return tr('king.lic_lane_unverified', login=login)
def reset_gate() -> None:
    """Untuk pengujian."""
    global _required
    _required = False
    set_current(empty())
def server_check(login: str) -> dict:
    """Satu panggilan ke server lisensi -> {\"ok\", \"status\" (LicenseClient.status), \"message\"}."""
    client = LicenseClient()
    ok, message = client.check(login)
    if ok:
        client.send_heartbeat()
    return {'ok': ok, 'status': client.status, 'message': message}
def _read_cache(path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
def _remember_ok(login: str, now: float, path) -> None:
    token = secure_store.protect(f'{login}|{now:.0f}')
    if not token:
        return
    else:
        data = _read_cache(path)
        data[login] = token
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding='utf-8')
        except OSError:
            return None
def _forget(login: str, path) -> None:
    data = _read_cache(path)
    if data.pop(login, None) is not None:
        try:
            path.write_text(json.dumps(data), encoding='utf-8')
        except OSError:
            return
def _last_ok(login: str, path) -> float:
    raw = secure_store.unprotect(_read_cache(path).get(login, ''))
    who, _sep, stamp = raw.partition('|')
    if who != login:
        return 0.0
    else:
        try:
            return float(stamp)
        except ValueError:
            return 0.0
def evaluate(login: str, checker, now: float | None, cache_path, entered: str | None=None) -> dict:
    """Status lisensi `login` (blocking - panggil di thread latar).\n\n    `entered` = ID Trading yang diisi pengguna di kartu akun. Wajib diisi dan wajib SAMA\n    dengan login yang aktif di terminal - server hanya ditanya bila keduanya cocok, jadi\n    ID berlisensi tidak bisa dipinjam untuk akun lain. None = tanpa pemeriksaan ini."""
    # ***<module>.evaluate: Failure: Different control flow
    path = cache_path or CACHE_PATH
    now = time.time() if now is None else now
    login = clean_id(login)
    out = empty(login, clean_id(entered))
    out['checked_at'] = now
    if not login:
        return out
    else:
        if entered is not None:
            if not out['entered']:
                out['status'] = MISSING
                return out
            else:
                if out['entered'] != login:
                    out['status'] = MISMATCH
                    return out
        result = checker(login)
        if result.get('ok'):
            _remember_ok(login, now, path)
            out.update(status=LICENSED, message=result.get('message', ''))
            return out
        else:
            if result.get('status') == 'UNLICENSED':
                _forget(login, path)
                out.update(status=UNLICENSED, message=result.get('message', ''))
            else:
                last = _last_ok(login, path)
                if last and 0 <= now - last <= GRACE_SECONDS:
                            out.update(status=LICENSED, grace=True, message=result.get('message', ''))
                out.update(status=UNVERIFIED, message=result.get('message', ''))