# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\trade_history.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Compilation Error
"""\ntrade_history.py\n=================\nLog histori sinyal & hasil trade KingAutoTrade ke CSV lokal, terpisah dari\nfolder MQL5/Files (murni penyimpanan sisi Python). Ini fondasi \"machine\nlearning\" v1: bukan model terlatih, tapi weighting sederhana berbasis\nwinrate historis per strategi (Support/Resistance, Breakout, Pola N)\nyang dipakai `autotrade_dashboard._run_one_scan` untuk membantu memilih\nstrategi mana yang dipakai saat probabilitas dari AI berdekatan.\n\nPakai CSV (bukan SQLite/database) dengan sengaja - lebih ringan, tidak ada\ndependency DB, dan bisa langsung dibuka di Excel/Notepad untuk inspeksi\nmanual. Tidak ada tabel rollup terpisah untuk winrate strategi - dihitung\non-the-fly dengan agregasi baris CSV tiap kali `get_strategy_weight`\ndipanggil (murah pada skala data ini: dipanggil paling banyak beberapa\nkali per siklus scan, minimal berjarak 5 detik, dan file signals tetap\nkecil - ribuan baris pun di-parse dalam hitungan milidetik dengan modul\n`csv` stdlib), jadi tidak perlu menjaga konsistensi 2 file sekaligus.\n\nSetiap fungsi buka & tutup file sendiri (tidak ada handle persisten) -\nhanya pernah dipanggil dari satu thread (scan-loop background), jadi tidak\nperlu locking.\n"""
import csv
from datetime import datetime, timedelta, timezone
from core.config import DATA_ROOT
from trading.trading_rules import is_autotrade_magic
DATA_DIR = DATA_ROOT / 'data'
SIGNALS_CSV = DATA_DIR / 'king_signals.csv'
MIN_SAMPLES = 5
HISTORY_WINDOW_DAYS = 3
BATCH_WINDOW_SECONDS = 30
FIELDNAMES = ['id', 'created_at', 'symbol', 'mode', 'strategy', 'probability', 'action', 'entry_type', 'entry', 'sl', 'tp', 'signal_id', 'outcome', 'pnl', 'closed_at', 'source']
def init_db() -> None:
    """Pastikan folder data/ dan king_signals.csv (dengan header) ada.\n    Idempotent - aman dipanggil tiap kali dashboard dibuka ATAU tiap kali\n    backtest dijalankan. Nama fungsi dipertahankan `init_db` (bukan\n    `init_csv`) supaya `autotrade_dashboard.py` tidak perlu diubah sama\n    sekali.\n\n    Juga menjalankan migrasi self-healing: kalau king_signals.csv sudah\n    ada dari sebelum kolom `source` ditambahkan, baca semua baris lama,\n    isi source=\"live\" (baris lama pasti dari live trading - backtest baru\n    ada setelah kolom ini ditambahkan), lalu tulis ulang dengan header\n    baru. Idempotent - begitu file sudah punya kolom `source`, migrasi ini\n    tidak melakukan apa-apa di panggilan berikutnya."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SIGNALS_CSV.exists():
        with open(SIGNALS_CSV, 'w', newline='', encoding='utf-8') as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        return
    else:
        with open(SIGNALS_CSV, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
    if header is not None and 'source' not in header:
            rows = _read_all_rows()
            for row in rows:
                row['source'] = 'live'
            _write_all_rows(rows)
def _read_all_rows() -> list[dict]:
    if not SIGNALS_CSV.exists():
        return []
    else:
        with open(SIGNALS_CSV, 'r', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
def _write_all_rows(rows: list[dict]) -> None:
    """Tulis ulang seluruh file secara atomik (tmp + rename) - dipakai\n    resolve_outcomes yang perlu update baris PENDING jadi WIN/LOSS (CSV\n    tidak punya update in-place, jadi rewrite penuh)."""
    tmp_path = SIGNALS_CSV.with_suffix(SIGNALS_CSV.suffix + '.tmp')
    with open(tmp_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(SIGNALS_CSV)
def record_signal(symbol, mode, strategy, probability, action, entry_type: str, entry: float, sl: float, tp: float, signal_id: int, source: str) -> None:
    """Catat sinyal baru yang baru saja ditulis ke signal.json. `strategy`/\n    `probability` None kalau sinyal berasal dari fallback mode-based\n    (bukan strategi S/R-Breakout-Pola N), tetap dicatat supaya\n    dataset mencakup semua trade, tidak hanya yang strategi-driven.\n    `source` default \"live\" - dipanggil apa adanya (tanpa argumen source)\n    oleh autotrade_dashboard.py, tidak perlu diubah. Untuk mencatat banyak\n    baris sekaligus (mis. hasil backtest), pakai `record_signals_bulk`\n    sebagai gantinya - fungsi ini re-baca seluruh file tiap panggilan\n    untuk hitung next_id (O(n) per panggilan), murah untuk live trading\n    yang jarang panggil, tapi O(n^2) kalau dipanggil ribuan kali\n    berturut-turut dalam loop."""
    # ***<module>.record_signal: Failure: Compilation Error
    init_db()
    rows = _read_all_rows()
    next_id = len(rows) + 1
    with open(SIGNALS_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow({'id': next_id, 'created_at': datetime.now(timezone.utc).isoformat(), 'symbol': symbol, 'mode': mode, 'strategy': strategy or '', 'probability': probability, 'action': action, 'entry_type': entry_type, 'entry': entry, 'sl': sl, 'tp': tp, 'signal_id': signal_id, 'outcome': 'PENDING', 'pnl': '', 'closed_at': '', 'source': source})
def record_signals_bulk(rows: list[dict]) -> None:
    """Tulis banyak baris sinyal sekaligus dalam SATU sesi baca+tulis -\n    dipakai backtest_engine.py yang bisa menghasilkan ribuan trade\n    simulasi (memanggil record_signal per baris akan jadi O(n^2) karena\n    tiap panggilan re-baca seluruh file untuk hitung next_id).\n\n    Tiap dict di `rows` harus berisi semua field FIELDNAMES KECUALI `id`\n    (dihitung otomatis, sekuensial mulai dari next_id) dan `created_at`\n    (diisi timestamp saat ini kalau tidak disediakan). Cocok untuk baris\n    backtest yang outcome-nya SUDAH diketahui (bukan PENDING) - backtest\n    tahu hasil trade secara sinkron dari simulasi forward-nya sendiri,\n    tidak perlu resolve_outcomes."""
    # ***<module>.record_signals_bulk: Failure: Compilation Error
    if not rows:
        return
    else:
        init_db()
        existing = _read_all_rows()
        next_id = len(existing) + 1
        with open(SIGNALS_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            row['id'] = next_id + i
            row.setdefault('created_at', datetime.now(timezone.utc).isoformat())
            row.setdefault('outcome', 'PENDING')
            row.setdefault('pnl', '')
            row.setdefault('closed_at', '')
            row.setdefault('source', 'backtest')
            writer.writerow(row)
def resolve_outcomes(mt5_module) -> int:
    """Cek deal history MT5 (window 3 hari terakhir) untuk sinyal yang masih\n    PENDING, tandai WIN/LOSS berdasarkan profit deal yang cocok (magic +\n    symbol + FIFO berdasar urutan waktu).\n\n    Grouping per \"batch\" penutupan (bukan per-deal individual) - dulu\n    dibutuhkan untuk fitur Martingale Layering (sudah dihapus total; 1\n    posisi Auto Trade sekarang SELALU = 1 closing deal, single-entry\n    murni). Grouping tetap dipertahankan sebagai jaring pengaman umum\n    (broker kadang membagi 1 closing jadi beberapa deal partial fill) -\n    deal-deal yang closing time-nya dalam window BATCH_WINDOW_SECONDS dari\n    deal PALING AWAL yang belum dipakai dianggap 1 batch, profit-nya\n    DIJUMLAHKAN sebelum dicocokkan ke 1 baris PENDING. Return jumlah baris\n    yang baru diresolusi."""
    # ***<module>.resolve_outcomes: Failure: Compilation Error
    since = datetime.now(timezone.utc) - timedelta(days=HISTORY_WINDOW_DAYS)
    deals = mt5_module.history_deals_get(since, datetime.now(timezone.utc))
    if not deals:
        return 0
    else:
        closing_deals = [d for d in deals if is_autotrade_magic(d.magic)]
        if not closing_deals:
            return 0
        else:
            closing_deals.sort(key=lambda d: d.time)
            rows = _read_all_rows()
            if not rows:
                return 0
            else:
                resolved = 0
                for row in rows:
                    if row['outcome'] != 'PENDING':
                        continue
                    else:
                        try:
                            created_ts = datetime.fromisoformat(row['created_at']).timestamp()
                        except (KeyError, ValueError):
                            created_ts = None
                        symbol_deals = [d for d in closing_deals if d.symbol == row['symbol'] and (created_ts is None or d.time >= created_ts)]
                        if not symbol_deals:
                            continue
                        else:
                            first = symbol_deals[0]
                            batch = [d for d in symbol_deals if abs(d.time - first.time) <= BATCH_WINDOW_SECONDS]
                            for d in batch:
                                closing_deals.remove(d)
                            pnl = sum((d.profit + d.swap + d.commission for d in batch))
                            last_time = max((d.time for d in batch))
                            row['outcome'] = 'WIN' if pnl > 0 else 'LOSS'
                            row['pnl'] = pnl
                            row['closed_at'] = datetime.fromtimestamp(last_time, tz=timezone.utc).isoformat()
                            resolved += 1
                if resolved:
                    _write_all_rows(rows)
                return resolved
def clear_history() -> None:
    """Hapus SELURUH riwayat sinyal (data/king_signals.csv) - dipanggil\n    tombol \"Clear History\" di card Machine Learning (SettingsPage), untuk\n    user yang ingin winrate-weighting mulai bersih dari nol lagi (mis.\n    setelah eksperimen strategi baru) tanpa perlu menonaktifkan fitur\n    Machine Learning itu sendiri. File ditulis ulang dengan header saja\n    (bukan dihapus filenya) - sama pola dengan init_db(), supaya baris\n    berikutnya langsung bisa ditulis tanpa perlu re-inisialisasi apapun."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SIGNALS_CSV, 'w', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
def get_strategy_weight(strategy: str) -> float:
    """Winrate historis strategi ini (0-1), dihitung dari agregasi\n    king_signals.csv langsung. Kalau sampel belum cukup (< MIN_SAMPLES\n    trade tercatat), return 0.5 (prior netral) supaya strategi baru/jarang\n    dipakai tidak langsung didiskualifikasi oleh noise sampel kecil."""
    wins = 0
    losses = 0
    for row in _read_all_rows():
        if row['strategy'] != strategy:
            continue
        else:
            if row['outcome'] == 'WIN':
                wins += 1
            else:
                if row['outcome'] == 'LOSS':
                    losses += 1
    total = wins + losses
    if total < MIN_SAMPLES:
        return 0.5
    else:
        return wins / total