# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\core\\license_client.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nlicense_client.py\n==================\nClient validasi lisensi KingAI, memakai server lisensi yang sama dengan\nQueenAI/EA MQL5 Bay (lihat queenai/trading/license_client.py).\n\nKingAI didaftarkan sebagai \"aplikasi\" tersendiri di server (bukan EA),\nlewat parameter ea_name=\"KingAI\" - supaya penggunaan KingAI kebaca\nterpisah dari QueenAI/EA lain di database license server, walau memakai\nendpoint & mekanisme cek yang sama persis.\n\nBeda dengan QueenAI:\n- Tidak ada aktivasi aplikasi. Lisensi berlaku PER AKUN MT5: worker tiap\n  akun (kingai/armada/worker.py) membaca login dari terminal yang tersambung\n  dan mengeceknya lewat kelas ini (lihat kingai/core/account_license.py).\n  Pair di akun tanpa lisensi tidak bisa di-Start. Batas jumlah ID trading\n  per member diatur di server lisensi.\n"""
from __future__ import annotations
import platform
import requests
from config import APP_NAME, APP_VERSION
from core.i18n import tr
LICENSE_SERVER_URL = 'https://roxyudeveloper.online/ea-license-server/license/check.php'
APP_NAME = 'KingAI'
APP_VERSION = APP_VERSION
LICENSE_CONTACT = '@bayuarissandi'
LICENSE_CHECK_INTERVAL = 3600
HEARTBEAT_INTERVAL = 3600
def _url_encode(text: str) -> str:
    import urllib.parse
    return urllib.parse.quote(text, safe='-_.~')
def _build_license_url(trading_id: str, action: str='check') -> str:
    """Susun URL cek lisensi - parameter senada dengan QueenAI/EA MQL5,\n    hanya field yang relevan untuk aplikasi desktop yang diisi."""
    params = {
        'account': trading_id,
        'action': action,
        'ea_name': APP_NAME,
        'version': APP_VERSION,
        'platform': platform.system(),
    }
    params = {'account': 'account', 'action': 'action', 'ea_name': 'ea_name', 'version': 'version', 'platform': 'platform'}
    query = '&'.join((f'{k}={_url_encode(str(v))}' for k, v in params.items()))
    return f'{LICENSE_SERVER_URL}?{query}'
def _clean_response(text: str) -> str:
    """Bersihkan BOM & karakter non-printable dari respons server."""
    if text.startswith('﻿'):
        text = text[1:]
    text = text.strip()
    cleaned = ''.join((ch for ch in text if 32 <= ord(ch) <= 126))
    return cleaned.upper()
class LicenseClient:
    """Menyimpan status lisensi selama aplikasi berjalan. ID trading yang\n    tervalidasi tersimpan di sini supaya heartbeat berkala bisa dikirim\n    tanpa user perlu connect ulang."""
    def __init__(self):
        self.trading_id = ''
        self.is_valid = False
        self.status = 'BELUM DICEK'
    def check(self, trading_id: str) -> tuple[bool, str]:
        """Validasi ID trading ke server lisensi. Return (valid, pesan)."""
        trading_id = trading_id.strip()
        if not trading_id:
            self.is_valid = False
            self.status = 'ID TRADING KOSONG'
            return (False, tr('license.id_empty'))
        else:
            if not trading_id.isdigit():
                self.is_valid = False
                self.status = 'ID TRADING TIDAK VALID'
                return (False, tr('license.id_not_numeric'))
            else:
                url = _build_license_url(trading_id, 'check')
                headers = {'User-Agent': f'{APP_NAME}/{APP_VERSION} (Python)'}
                try:
                    resp = requests.get(url, headers=headers, timeout=15)
                except requests.exceptions.RequestException as e:
                    self.is_valid = False
                    self.status = 'GAGAL TERHUBUNG'
                    return (False, tr('license.connect_fail', error=e))
                response_text = _clean_response(resp.text)
                if response_text == 'OK':
                    self.trading_id = trading_id
                    self.is_valid = True
                    self.status = 'LICENSED'
                    return (True, tr('license.valid'))
                else:
                    self.is_valid = False
                    self.status = 'UNLICENSED'
                    return (False, tr('license.invalid', trading_id=trading_id, contact=LICENSE_CONTACT))
    def send_heartbeat(self) -> None:
        """Kirim heartbeat ke server (dipanggil berkala selama aplikasi\n        terbuka & lisensi valid). Kegagalan heartbeat tidak mengubah status\n        valid yang sudah ada - hanya percobaan berikutnya yang menentukan."""
        if not self.is_valid or not self.trading_id:
            return None
        else:
            url = _build_license_url(self.trading_id, 'heartbeat')
            headers = {'User-Agent': f'{APP_NAME}/{APP_VERSION} (Python)'}
            try:
                requests.get(url, headers=headers, timeout=5)
            except requests.exceptions.RequestException:
                return None