# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\account_mode.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\naccount_mode.py\n===============\nMode posisi akun MT5: HEDGING atau NETTING.\n\n- Hedging: tiap order membuka posisi sendiri; magic number memisahkan posisi\n  milik KingAI dari EA lain / trade manual di symbol yang sama.\n- Netting: satu posisi bersih per symbol. Order baru DIGABUNG ke posisi yang\n  sudah ada apa pun magic-nya, jadi magic tidak bisa memisahkan posisi.\n\nMode dideteksi dari `mt5.account_info().margin_mode`\n(ENUM_ACCOUNT_MARGIN_MODE: 0 retail netting, 1 exchange, 2 retail hedging).\nPengguna boleh memilih manual per akun (Pengaturan › Armada); pilihan \"auto\"\nyang gagal dideteksi membuat mode tidak diketahui -> Start ditolak sampai\npengguna memilih Hedging atau Netting sendiri.\n\nSatu proses worker = satu akun, jadi keadaan disimpan di level modul.\n"""
from __future__ import annotations
import threading
AUTO, HEDGING, NETTING = ('auto', 'hedging', 'netting')
CHOICES = (AUTO, HEDGING, NETTING)
_MARGIN_RETAIL_NETTING, _MARGIN_EXCHANGE, _MARGIN_RETAIL_HEDGING = (0, 1, 2)
_lock = threading.Lock()
_state = {'choice': AUTO, 'mode': None, 'detected': None, 'resolved': False}
def clean_choice(choice) -> str:
    return choice if choice in CHOICES else AUTO
def detect(account_info) -> str | None:
    """Mode dari account_info MT5, None kalau tidak bisa dibaca."""
    raw = getattr(account_info, 'margin_mode', None) if account_info is not None else None
    try:
        raw = int(raw)
    except (TypeError, ValueError):
        return None
    if raw == _MARGIN_RETAIL_HEDGING:
        return HEDGING
    else:
        if raw in (_MARGIN_RETAIL_NETTING, _MARGIN_EXCHANGE):
            return NETTING
        else:
            return None
def resolve(choice, account_info) -> dict:
    """{\"choice\", \"mode\", \"detected\"} - mode efektif: pilihan manual, atau hasil deteksi (bisa None)."""
    choice = clean_choice(choice)
    detected = detect(account_info)
    mode = detected if choice == AUTO else choice
    return {'choice': choice, 'mode': mode, 'detected': detected}
def configure(choice, account_info) -> dict:
    """Simpan hasil resolve untuk proses ini. Return salinannya."""
    result = resolve(choice, account_info)
    with _lock:
        _state.update(result, resolved=True)
        return dict(_state)
def set_choice(choice) -> None:
    """Pilihan pengguna berubah - mode dihitung ulang saat `ensure` berikutnya."""
    with _lock:
        choice = clean_choice(choice)
        if choice != _state['choice']:
            _state.update(choice=choice, resolved=False)
def ensure(mt5_module) -> str | None:
    """Mode efektif; deteksi ulang dari MT5 bila belum pernah / pilihan berubah."""
    with _lock:
        if _state['resolved']:
            return _state['mode']
        else:
            choice = _state['choice']
    info = None
    if mt5_module is not None:
        try:
            info = mt5_module.account_info()
        except Exception:
            info = None
    if info is None and choice == AUTO:
            return
    return configure(choice, info)['mode']
def current() -> str | None:
    with _lock:
        return _state['mode']
def is_netting() -> bool:
    return current() == NETTING
def snapshot() -> dict:
    with _lock:
        return {k: _state[k] for k in ['choice', 'mode', 'detected']}
def reset() -> None:
    """Untuk pengujian."""
    with _lock:
        _state.update(choice=AUTO, mode=None, detected=None, resolved=False)