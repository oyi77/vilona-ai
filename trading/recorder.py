# Source Generated with Decompyle++
# File: recorder.pyc (Python 3.10)

'''
recorder.py
============
"Pencatat Istana" - satu-satunya pintu resmi ke data histori trading
(king_signals.csv lewat trade_history.py). Murni kode, tanpa LLM.

Kenapa perlu (bukan sekadar membungkus): trade_history.py didesain
single-thread (scan-loop saja, lihat docstring-nya). Begitu ada fitur
Export/Import di Settings (main thread) yang membaca/menulis file yang
sama - plus Clear History yang juga dari main thread - asumsi itu patah:
export yang berjalan bersamaan dengan record_signal dari scan-thread bisa
membaca file setengah tertulis. Recorder menambah satu RLock yang
menserialkan SEMUA akses, jadi trade_history.py sendiri tidak perlu
diubah sama sekali.

Tulisan CSV berlangsung hitungan milidetik, jadi TIDAK pakai antrian/
worker-thread async - scan-loop sendiri sudah mentoleransi latensi
puluhan detik (menunggu HTTP AI 45 detik), menahan lock beberapa ms
tidak terasa. Antrian async hanya menambah titik gagal baru.

Juga berisi normalisasi symbol broker untuk data yang DIBAGIKAN antar
user: "XAUUSD.m" / "XAUUSDm" / "GOLD" di broker berbeda adalah instrumen
yang sama - tanpa normalisasi, dataset gabungan dari banyak user akan
menganggapnya instrumen berbeda dan agregasi ML-nya pecah.

Pakai singleton `recorder` di bawah - halaman auto trade (scan thread)
dan Settings Export/Import/Clear (main thread) HARUS memakai instance
yang sama supaya lock-nya benar-benar melindungi.
'''
import csv
import threading
from datetime import datetime, timezone
from trading import trade_history
SYMBOL_ALIASES = {
    'GOLD': 'XAUUSD',
    'XAU': 'XAUUSD',
    'SILVER': 'XAGUSD',
    'XAG': 'XAGUSD',
    'USOIL': 'WTIUSD',
    'UKOIL': 'XBRUSD',
    'DOW': 'US30',
    'NAS': 'US100',
    'NASDAQ': 'US100',
    'SPX': 'US500',
    'DAX': 'DE40' }
_SUFFIX_SEPARATORS = '.-_#!$ '

def normalize_symbol(symbol = None):
    '''"XAUUSD.m" -> "XAUUSD", "XAUUSDm" -> "XAUUSD", "gold" -> "XAUUSD".
    1. Potong di separator suffix broker pertama (titik, underscore, dst).
    2. Kalau campuran huruf besar-kecil, buang huruf KECIL di ekor -
       suffix micro/cent broker hampir selalu lowercase (XAUUSDm, EURUSDc)
       sementara nama instrumennya uppercase. Nama yang seluruhnya
       lowercase/uppercase tidak disentuh aturan ini (tidak ada sinyal
       mana bagian suffix-nya).
    3. Uppercase, lalu petakan alias yang dikenal ke nama kanonik.'''
    if not symbol:
        pass
    s = ''.strip()
    for sep in _SUFFIX_SEPARATORS:
        idx = s.find(sep)
        if idx > 0:
            s = s[:idx]
    if not s and s.isupper() and s.islower():
        s = s.rstrip('abcdefghijklmnopqrstuvwxyz')
    s = s.upper()
    return SYMBOL_ALIASES.get(s, s)

EXPORT_FIELDS = [
    'created_at',
    'symbol',
    'symbol_raw',
    'mode',
    'strategy',
    'probability',
    'action',
    'entry_type',
    'entry',
    'sl',
    'tp',
    'outcome',
    'pnl',
    'closed_at',
    'source']
IMPORT_REQUIRED = {
    'strategy',
    'outcome',
    'symbol',
    'action'}
VALID_OUTCOMES = {
    'WIN',
    'LOSS'}
VALID_ACTIONS = {
    'BUY',
    'SELL'}

class Recorder:
    
    def __init__(self):
        self._lock = threading.RLock()

    
    def init_db(self = None):
        with self._lock:
            trade_history.init_db()
            None(None, None, None)
            return None
            with None:
                if not None:
                    pass

    
    def record_signal(self = None, **kwargs):
        pass
    # WARNING: Decompyle incomplete

    
    def resolve_outcomes(self = None, mt5_module = None):
        with self._lock:
            None(None, None, None)
            return trade_history.resolve_outcomes(mt5_module)
            with None:
                if not None:
                    pass

    
    def get_strategy_weight(self = None, strategy = None):
        with self._lock:
            None(None, None, None)
            return trade_history.get_strategy_weight(strategy)
            with None:
                if not None:
                    pass

    
    def clear_history(self = None):
        with self._lock:
            trade_history.clear_history()
            None(None, None, None)
            return None
            with None:
                if not None:
                    pass

    
    def export_ml_csv(self = None, path = None):
        '''Tulis dataset ML (kolom whitelist, symbol dinormalisasi) ke
        `path`. Return (sukses, jumlah_baris, pesan_error). Hanya baris
        dengan outcome final (WIN/LOSS) yang diekspor - baris PENDING
        belum punya label hasil, tidak berguna untuk pembelajaran.'''
        with self._lock:
            rows = trade_history._read_all_rows()
            None(None, None, None)
        with None:
            if not None:
                pass
        exported = 0
    # WARNING: Decompyle incomplete

    
    def import_ml_csv(self = None, path = None):
        '''Baca file dataset ML (hasil export_ml_csv milik user lain) dan
        tambahkan ke histori lokal dengan source="imported". Return
        (sukses, jumlah_masuk, jumlah_dilewati, pesan_error).

        Validasi per baris (baris tidak valid DILEWATI, bukan
        menggagalkan seluruh import - file dari luar tidak bisa
        dipercaya bersih): action harus BUY/SELL, outcome harus WIN/LOSS,
        strategy tidak kosong. Duplikat (created_at+symbol+action sama
        dengan baris yang sudah ada) dilewati supaya import file yang
        sama dua kali tidak menggandakan data & merusak winrate.'''
        pass
    # WARNING: Decompyle incomplete


recorder = Recorder()
