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
    """Thread-safe wrapper around trade_history — serialises ALL access
    with one RLock so main-thread export/import and scan-thread
    record_signal never race on king_signals.csv."""

    def __init__(self):
        self._lock = threading.RLock()

    def init_db(self) -> None:
        with self._lock:
            trade_history.init_db()

    def record_signal(self, symbol: str, mode: str, strategy=None,
                      probability=None, action: str = '', entry_type: str = '',
                      entry: float = 0.0, sl: float = 0.0, tp: float = 0.0,
                      signal_id: int = 0, source: str = 'live') -> None:
        with self._lock:
            trade_history.record_signal(
                symbol=symbol, mode=mode, strategy=strategy,
                probability=probability, action=action, entry_type=entry_type,
                entry=entry, sl=sl, tp=tp, signal_id=signal_id, source=source,
            )

    def resolve_outcomes(self, mt5_module) -> int:
        with self._lock:
            return trade_history.resolve_outcomes(mt5_module)

    def get_strategy_weight(self, strategy: str) -> float:
        with self._lock:
            return trade_history.get_strategy_weight(strategy)

    def clear_history(self) -> None:
        with self._lock:
            trade_history.clear_history()

    def export_ml_csv(self, path):
        """Tulis dataset ML (kolom whitelist, outcome=WIN/LOSS saja) ke path.
        Return (ok, n_exported, error_msg)."""
        with self._lock:
            try:
                rows = trade_history._read_all_rows()
                final = [r for r in rows if r.get('outcome') in ('WIN', 'LOSS')]
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=trade_history.FIELDNAMES)
                    writer.writeheader()
                    for r in final:
                        writer.writerow(r)
                return (True, len(final), '')
            except Exception as e:
                return (False, 0, str(e))

    def import_ml_csv(self, path):
        """Baca dataset ML dari path, tambahkan source='imported'.
        Return (ok, n_imported, n_skipped, error_msg). Baris tidak valid
        (action bukan BUY/SELL, outcome bukan WIN/LOSS, strategy kosong)
        dilewati per baris."""
        with self._lock:
            try:
                import csv
                with open(path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    incoming = [dict(r) for r in reader]
            except Exception as e:
                return (False, 0, 0, str(e))
            existing_keys = {
                (r.get('created_at', ''), r.get('symbol', ''), r.get('action', ''))
                for r in trade_history._read_all_rows()
            }
            imported = skipped = 0
            for row in incoming:
                if row.get('action') not in ('BUY', 'SELL'):
                    skipped += 1
                    continue
                if row.get('outcome') not in ('WIN', 'LOSS'):
                    skipped += 1
                    continue
                if not row.get('strategy'):
                    skipped += 1
                    continue
                key = (row.get('created_at', ''), row.get('symbol', ''), row.get('action', ''))
                if key in existing_keys:
                    skipped += 1
                    continue
                existing_keys.add(key)
                row['source'] = 'imported'
                trade_history.record_signals_bulk([row])
                imported += 1
            return (True, imported, skipped, '')

recorder = Recorder()
