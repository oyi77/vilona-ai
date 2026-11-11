# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\trading_rules.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Different bytecode
"""\ntrading_rules.py\n=================\nAturan trading murni (tanpa dependency Qt/MT5/AI) yang dipakai BAIK oleh\nlive trading (autotrade_dashboard.py, trade_executor.py) MAUPUN backtest\n(backtest_engine.py) - satu sumber kebenaran supaya perubahan tuning\n(floor SL/TP, logika entry adaptif, magic number) tidak perlu\ndiduplikasi/berisiko drift antar modul.\n\nAwalnya (`MIN_SLTP_POINTS`, `_resolve_adaptive_entry_type`) adalah bagian\ndari class AutoTradeDashboard di autotrade_dashboard.py - diekstrak ke\nsini karena keduanya murni fungsi/konstanta tanpa state UI sama sekali.\n"""
MAGIC = 770321
DEVIATION_POINTS = 20
MAGIC_CODEX = 770322
MAGIC_RETIRED = 770323
MAGIC_MAX = 999999999
_lane_magic: dict[str, int] = {}
_known_magics: frozenset[int] = frozenset()
def validate_magic(value) -> str | None:
    """None kalau `value` boleh dipakai sebagai magic pair (None = bawaan), selain itu kode\n    masalah: \"range\" (bukan bilangan 1..MAGIC_MAX) atau \"reserved\" (magic fitur lain)."""
    # ***<module>.validate_magic: Failure: Compilation Error
    if value is None:
        return
    else:
        if isinstance(value, bool) or (isinstance(value, float) and (not value.is_integer())):
            return 'range'
        else:
            try:
                magic = int(value)
            except (TypeError, ValueError):
                return 'range'
            if not 1 <= magic <= MAGIC_MAX:
                return 'range'
            else:
                if magic in (MAGIC_CODEX, MAGIC_RETIRED):
                    return 'reserved'
                else:
                    return None
def set_lane_magics(mapping: dict[str, int | None]) -> None:
    """Worker: peta symbol -> magic lane (None = MAGIC bawaan). Diganti utuh tiap sinkron."""
    global _lane_magic
    _lane_magic = {str(sym).strip().upper(): int(m) for sym, m in mapping.items() if not str(sym).strip() or m is not None}
def set_known_magics(magics) -> None:
    """Hub: magic semua lane (lintas akun) - hanya untuk mengenali trade KingAI."""
    global _known_magics
    _known_magics = frozenset((int(m) for m in magics if m is not None))
class LaneSymbol(str):
    """Symbol milik satu lane, membawa magic lane itu. Dipakai bila beberapa lane (mode berbeda) memakai\n    symbol yang sama di satu akun: peta symbol -> magic tak cukup, jadi magic ikut terbawa di string-nya."""
    magic: int | None = None
    def __new__(cls, text: str, magic: int | None=None):
        obj = super().__new__(cls, text)
        obj.magic = magic
        return obj
    def strip(self, *args):
        return LaneSymbol(str.strip(self, *args), self.magic)
def magic_for(symbol: str) -> int:
    """Magic yang dipakai Auto Trade untuk `symbol` di proses ini."""
    own = getattr(symbol, 'magic', None)
    if own:
        return int(own)
    else:
        return _lane_magic.get((symbol or '').strip().upper(), MAGIC)
def autotrade_magics() -> frozenset[int]:
    return frozenset({MAGIC, *_lane_magic.values(), *_known_magics})
def is_autotrade_magic(magic) -> bool:
    try:
        return int(magic) in autotrade_magics()
    except (TypeError, ValueError):
        return False
RISK_LEVELS = ['low', 'medium', 'high', 'expert']
RISK_PERCENT = {'low': 0.5, 'medium': 1.0, 'high': 2.0, 'expert': 3.0}
MIN_SLTP_POINTS = {'scalping': {'low': {'sl': 800, 'tp': 1600}, 'medium': {'sl': 1000, 'tp': 2000}, 'high': {'sl': 1300, 'tp': 2400}, 'expert': {'sl': 1600, 'tp': 2800}}, 'intraday': {'low': {'sl': 2000, 'tp': 3200}, 'medium': {'sl': 2500, 'tp': 4000}, 'high': {'sl': 3200, 'tp': 4800}, 'expert': {'sl': 4000, 'tp': 5600}}, 'swing': {'low': {'sl': 5000, 'tp': 8000}, 'medium': {'sl': 6000, 'tp': 10000}, 'high': {'sl': 7500, 'tp': 12000}, 'expert': {'sl': 9000, 'tp': 14000}}}
def resolve_min_sltp(mode: str, risk_level: str='medium') -> dict:
    """Ambil floor SL/TP (points) untuk kombinasi mode x level risiko -\n    satu titik akses supaya caller (base_autotrade_page.py/\n    manual_autotrade_page.py) tidak perlu tahu struktur nested dict-nya.\n    mode/risk_level tidak dikenal -> fallback ke intraday/medium (representasi\n    paling seimbang), TIDAK raise - caller (mis. field UI kosong sesaat)\n    tidak boleh crash gara-gara kombinasi belum lengkap terisi."""
    by_mode = MIN_SLTP_POINTS.get(mode, MIN_SLTP_POINTS['intraday'])
    return by_mode.get(risk_level, by_mode['medium'])
RISK_MANUAL = 'manual'
MANUAL_RISK_PERCENT_MAX = 10.0
def resolve_risk(mode: str, risk_level: str='medium', custom: dict | None=None) -> dict:
    """Satu titik akses aturan risiko: {\"percent\", \"sl\", \"tp\"}. Preset dari\n    RISK_PERCENT x MIN_SLTP_POINTS; level \"manual\" + `custom` (dict berisi\n    percent/sl/tp dari card Risiko) memakai angka pengguna apa adanya."""
    if risk_level == RISK_MANUAL and custom:
        return {'percent': float(custom['percent']), 'sl': float(custom['sl']), 'tp': float(custom['tp'])}
    else:
        floor = resolve_min_sltp(mode, risk_level)
        return {'percent': RISK_PERCENT.get(risk_level, RISK_PERCENT['medium']), 'sl': floor['sl'], 'tp': floor['tp']}
def validate_manual_risk(percent: float, sl: float, tp: float) -> str | None:
    """None kalau isian risiko manual masuk akal, selain itu kunci pesan\n    (dipakai UI): percent harus 0 < x <= MANUAL_RISK_PERCENT_MAX, SL/TP > 0."""
    # ***<module>.validate_manual_risk: Failure: Compilation Error
    if not 0 < percent <= MANUAL_RISK_PERCENT_MAX:
        return 'percent'
    else:
        if sl <= 0 or tp <= 0:
            return 'sltp'
        else:
            return None
def resolve_auto_lot(balance: float, risk_level: str, sl_points: float, point_value: float, min_lot: float=0.01, lot_step: float=0.01, max_lot: float | None=None, risk_percent: float | None=None) -> float:
    """Position sizing otomatis - lot = (modal x %risk_level) / (jarak_SL\n    dalam MATA UANG AKUN), dibulatkan KE BAWAH ke `lot_step` terdekat supaya\n    tidak pernah melebihi risk yang diminta akibat pembulatan. `point_value`\n    = nilai 1 point dalam mata uang akun UNTUK 1 LOT PENUH (dari\n    mt5.symbol_info(symbol).trade_tick_value, DIKONVERSI ke basis \"per point\"\n    yang sama dengan sl_points - caller bertanggung jawab menyamakan basis\n    ini, sama seperti seluruh modul lain di sini yang selalu memakai\n    info.point asli broker, BUKAN 10**-digits).\n\n    balance<=0, sl_points<=0, atau point_value<=0 -> return `min_lot` (data\n    tidak valid/tidak bisa dihitung - caller WAJIB treat ini sebagai fallback\n    aman, BUKAN mengirim lot 0.0 yang akan ditolak MT5).\n\n    `risk_percent` (opsional) menggantikan RISK_PERCENT[risk_level] - dipakai\n    level Risiko \"manual\"."""
    if balance <= 0 or sl_points <= 0 or point_value <= 0:
        return min_lot
    else:
        if risk_percent is None or risk_percent <= 0:
            risk_percent = RISK_PERCENT.get(risk_level, RISK_PERCENT['medium'])
        risk_amount = balance * (risk_percent / 100.0)
        raw_lot = risk_amount / (sl_points * point_value)
        steps = raw_lot / lot_step
        lot = int(steps) * lot_step
        lot = max(lot, min_lot)
        if max_lot is not None:
            lot = min(lot, max_lot)
        return round(lot, 2)
def resolve_adaptive_entry_type(entry_type, entry, market_price, is_buy, spread_points, min_sl_points, point) -> str:
    """Tentukan MARKET/STOP/LIMIT otomatis dari posisi entry (AI atau\n    strategi backtest) relatif ke harga pasar saat ini. BUY: entry di atas\n    ask -> harga harus naik dulu -> STOP; entry di/bawah ask -> LIMIT\n    (pullback) kecuali dalam toleransi -> MARKET. Mirror untuk SELL\n    terhadap bid.\n\n    Toleransi MARKET SENGAJA diperketat lagi (1% dari floor SL, sebelumnya\n    2%, awalnya 5%) - prioritas eksekusi diarahkan ke pending order\n    (STOP/LIMIT), bukan MARKET, karena entry pending secara natur masuk di\n    harga lebih baik (area S/R/pullback) dan memungkinkan SL lebih ketat,\n    alih-alih mengejar harga di tengah pergerakan. MARKET sekarang HANYA\n    dipakai kalau entry AI benar-benar (nyaris) persis di harga pasar saat\n    ini - bukan lagi \"cukup dekat\". Basis toleransi tetap `spread_points *\n    2` sebagai floor bawah (jangan sampai toleransi lebih sempit dari\n    spread itu sendiri, yang akan membuat SEMUA entry jatuh ke STOP/LIMIT\n    walau benar-benar di harga pasar - spread sendiri sudah menciptakan\n    selisih bid/ask sebesar itu)."""
    if entry_type != 'ADAPTIF':
        return entry_type
    else:
        tolerance = max(spread_points * 2, min_sl_points * 0.01) * point
        if abs(entry - market_price) <= tolerance:
            return 'MARKET'
        else:
            if is_buy:
                return 'STOP' if entry > market_price else 'LIMIT'
            else:
                return 'STOP' if entry < market_price else 'LIMIT'
def resolve_percent_to_points(percent: float, price: float, point: float) -> float:
    """Konversi jarak PERSENTASE HARGA ke POINTS mentah - dipakai mode\n    \"Persen Harga\" di UI Auto Trade (base_autotrade_page.py/\n    manual_autotrade_page.py) sebagai alternatif input poin mentah, supaya\n    jarak yang sama (mis. 0.075%) proporsional di symbol apapun terlepas\n    skala harganya (XAUUSD @4000 vs Vol_20 @728000 vs EURUSD @1.08).\n\n    Formula: points = (percent/100) * price / point.\n    Contoh: 0.075% dari harga 4000.00 dengan point 0.01\n            -> (0.075/100) * 4000.00 / 0.01 = 300.0 poin.\n\n    price<=0, point<=0, atau percent<=0 -> return 0.0 (data harga tidak\n    valid atau jarak tidak bermakna - caller WAJIB treat ini sebagai\n    \"tidak bisa dihitung\", bukan mengirim SL/TP 0 begitu saja)."""
    if price <= 0 or point <= 0 or percent <= 0:
        return 0.0
    else:
        return percent / 100.0 * price / point
def resolve_points_to_percent(points: float, price: float, point: float) -> float:
    """Kebalikan resolve_percent_to_points - dipakai preview live UI untuk\n    menampilkan berapa % yang berlaku dari poin yang sedang aktif."""
    if price <= 0 or point <= 0 or points <= 0:
        return 0.0
    else:
        return points * point / price * 100.0
def pip_size_in_points(digits: int) -> float:
    """Berapa point mentah MT5 = 1 pip standar broker, dari jumlah digit\n    harga symbol. Konvensi umum forex: 1 pip = urutan digit KEDUA dari\n    belakang harga (bukan yang terakhir - yang terakhir itu \"point\"/\n    fractional pip). Broker 5-digit (mis. EURUSD 1.08123) & 3-digit\n    (pair JPY, mis. USDJPY 148.123) sama-sama punya \"1 digit ekstra\" itu -\n    pip = 10 point. Broker 4-digit/2-digit lama (tanpa digit ekstra) ->\n    pip = 1 point (sama dengan point mentah, tidak ada sub-pip).\n    Digits lain (indeks/logam dengan skala sendiri, mis. XAUUSD 2 digit)\n    -> fallback 1 point = 1 pip, tidak ada konvensi pip baku untuk itu."""
    if digits in [3, 5]:
        return 10.0
    else:
        return 1.0
def resolve_pips_to_points(pips: float, digits: int) -> float:
    """Konversi jarak dalam PIPS standar broker ke POINTS mentah MT5 -\n    dipakai mode \"Pips\" di UI Auto Trade, alternatif dari Poin mentah yang\n    sudah ada. Lihat pip_size_in_points untuk aturan konversi per digit."""
    if pips <= 0 or digits <= 0:
        return 0.0
    else:
        return pips * pip_size_in_points(digits)
ATR_PERIOD_DEFAULT = 14
def atr_from_rates(rates, period: int=ATR_PERIOD_DEFAULT) -> float:
    """ATR (rata-rata True Range `period` candle terakhir, dalam HARGA) dari\n    rates MT5 (array/list dengan field high/low/close). 0 kalau data kurang."""
    # ***<module>.atr_from_rates: Failure: Compilation Error
    try:
        highs = [float(r['high']) for r in rates]
        lows = [float(r['low']) for r in rates]
        closes = [float(r['close']) for r in rates]
    except (TypeError, KeyError, IndexError, ValueError):
        return 0.0
    if period < 1 or len(closes) <= period:
        return 0.0
    else:
        trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(len(closes) - period, len(closes))]
        return sum(trs) / period
def resolve_atr_to_points(multiplier: float, atr_price: float, point: float) -> float:
    """Mode \"ATR\" di UI Auto Trade: jarak = multiplier x ATR (harga), lalu\n    dikonversi ke POINTS mentah MT5 (trade_executor hanya menerima poin)."""
    if multiplier <= 0 or atr_price <= 0 or point <= 0:
        return 0.0
    else:
        return multiplier * atr_price / point
def resolve_points_to_pips(points: float, digits: int) -> float:
    """Kebalikan resolve_pips_to_points - dipakai preview live UI."""
    if points <= 0 or digits <= 0:
        return 0.0
    else:
        return points / pip_size_in_points(digits)