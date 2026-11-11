# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\strategy_validators.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Compilation Error
"""\nstrategy_validators.py\n=======================\nValidasi Python MURNI (tanpa dependency Qt/MT5/AI, sama filosofi dengan\ntrading_rules.py) untuk 4 strategi KingAI: Support/Resistance (SNR),\nBreakout, Pola N, SMC/ICT.\n\nLATAR BELAKANG: sebelum modul ini ada, kelima strategi TIDAK punya logika\nkeputusan Python sama sekali - semua data (RSI/MACD/trend/S/R/SMC) dikirim\nmentah sebagai teks ke LLM, dan LLM sendiri yang menilai valid/tidaknya\nsecara kualitatif. Ini menyebabkan sinyal terasa \"chaos\"/tidak konsisten\nkarena tidak ada aturan matematis yang mengikat.\n\nModul ini menggantikan validasi kualitatif LLM dengan aturan deterministik:\ntiap `validate_*` menghasilkan pass/fail TEGAS dari data yang sudah dihitung\nmt5_bridge.py - HANYA strategi yang LOLOS di sini yang boleh dikirim ke AI\nuntuk dinilai probabilitas/narasinya (lihat openrouter_client.py, section\nSTRATEGI) dan HANYA yang lolos yang boleh dieksekusi jadi order (lihat\nbase_autotrade_page._select_strategy_candidate). Strategi yang TIDAK lolos\ntetap DITAMPILKAN ke user (label eksplisit LOLOS/TIDAK LOLOS, bukan\ndisembunyikan total - keputusan user) tapi tidak pernah dikirim ke AI/\ndieksekusi.\n\nSemua fungsi murni (input dict/list/angka, output dict) - bisa dites tanpa\nMT5/Qt sama sekali.\n"""
from trading import trading_rules
_BREAKOUT_MIN_ATR_RATIO = 0.3
_BREAKOUT_MAX_ATR_RATIO = 3.0
_SNR_REACT_PERCENT = 0.1
def _uniform_result(passed, direction, score, reasons, metrics: dict) -> dict:
    # ***<module>._uniform_result: Failure: Compilation Error
    return {'passed': passed, 'direction': direction, 'score': score, 'reasons': reasons, 'metrics': metrics}
def validate_snr(sr_levels: list[dict], price: float, point: float) -> dict:
    """Support/Resistance valid HANYA kalau harga sekarang sedang BEREAKSI\n    (dalam radius kecil, persentase harga) di salah satu level yang SUDAH\n    tervalidasi (`valid=True`, lihat mt5_bridge._score_sr_levels - skor dari\n    touch-count + bobot timeframe, BUKAN sekadar level terdekat seperti\n    logika lama)."""
    # ***<module>.validate_snr: Failure: Compilation Error
    if price <= 0 or point <= 0:
        return _uniform_result(False, None, 0.0, ['data harga tidak valid'], {})
    else:
        react_points = trading_rules.resolve_percent_to_points(_SNR_REACT_PERCENT, price, point)
        if react_points <= 0:
            return _uniform_result(False, None, 0.0, ['toleransi reaksi tidak bisa dihitung'], {})
        else:
            react_distance = react_points * point
            valid_levels = [lv for lv in sr_levels if lv.get('valid')]
            candidates = [lv for lv in valid_levels if abs(lv['price'] - price) <= react_distance]
            if not candidates:
                return _uniform_result(False, None, 0.0, ['harga tidak sedang bereaksi di level valid manapun'], {'valid_level_count': len(valid_levels)})
            else:
                nearest = min(candidates, key=lambda lv: abs(lv['price'] - price))
                direction = 'BULLISH' if nearest['type'] == 'SUPPORT' else 'BEARISH'
                return _uniform_result(True, direction, float(nearest.get('score') or 0), [f"harga bereaksi di {nearest['type'].lower()} {nearest['price']}"], {'level': nearest})
def _breakout_score(distance_ratio: float) -> float:
    """Skor breakout (50-100) yang PUNCAK di sweet-spot antara\n    _BREAKOUT_MIN_ATR_RATIO dan _BREAKOUT_MAX_ATR_RATIO, BUKAN monoton\n    naik - dekat batas minimum (breakout baru saja terjadi, follow-through\n    belum banyak) atau dekat batas maksimum (sudah lari jauh, mendekati\n    exhaustion) sama-sama kurang ideal dibanding titik tengah rentang."""
    span = _BREAKOUT_MAX_ATR_RATIO - _BREAKOUT_MIN_ATR_RATIO
    midpoint = _BREAKOUT_MIN_ATR_RATIO + span / 2.0
    normalized_dist = abs(distance_ratio - midpoint) / (span / 2.0)
    return 100.0 - min(1.0, normalized_dist) * 50.0
def validate_breakout(sr_levels: list[dict], tf_data: dict, price: float) -> dict:
    """Breakout x SNR: valid HANYA kalau candle close TEGAS melewati level\n    S/R yang SUDAH tervalidasi (bukan level lemah/belum teruji) DISERTAI\n    follow-through (candle berikutnya melanjutkan arah yang sama) dan jarak\n    breakout SIGNIFIKAN tapi TIDAK TERLALU JAUH relatif ATR (menyaring\n    noise kecil DAN exhaustion move yang sudah telat, lihat\n    _BREAKOUT_MIN_ATR_RATIO/_BREAKOUT_MAX_ATR_RATIO) - kombinasi ini\n    (\"Breakout x SNR\") sebelumnya tidak ada sama sekali di kode (Breakout\n    100% teks prompt tanpa data S/R yang benar-benar divalidasi). Skor\n    breakout PUNCAK di tengah rentang (jauh cukup meyakinkan, belum\n    terlalu jauh utk dikejar) - BUKAN monoton naik seiring jarak\n    (breakout yang sudah lari sangat jauh dari level LEBIH BERISIKO\n    dikejar via MARKET, bukan lebih meyakinkan, walau follow-through-nya\n    tetap ada)."""
    # ***<module>.validate_breakout: Failure: Compilation Error
    closes = tf_data.get('closes') or []
    atr = tf_data.get('atr', 0.0)
    if len(closes) < 2 or atr <= 0:
        return _uniform_result(False, None, 0.0, ['data candle/ATR tidak cukup'], {})
    else:
        prev_close, last_close = (closes[(-2)], closes[(-1)])
        valid_resistances = sorted([lv for lv in sr_levels if lv.get('valid') and lv['type'] == 'RESISTANCE' and (lv['price'] <= prev_close)], key=lambda lv: -lv['price'])
        valid_supports = sorted([lv for lv in sr_levels if lv.get('valid') and lv['type'] == 'SUPPORT' and (lv['price'] >= prev_close)], key=lambda lv: lv['price'])
        if valid_resistances:
            level = valid_resistances[0]
            broke = prev_close > level['price']
            follow_through = last_close > prev_close
            distance_ratio = (prev_close - level['price']) / atr if broke else 0.0
            if broke and follow_through and (_BREAKOUT_MIN_ATR_RATIO <= distance_ratio <= _BREAKOUT_MAX_ATR_RATIO):
                return _uniform_result(True, 'BULLISH', _breakout_score(distance_ratio), [f"close {prev_close:.5f} menembus resistance valid {level['price']:.5f} ({distance_ratio:.2f}x ATR) + follow-through"], {'broken_level': level, 'distance_atr_ratio': round(distance_ratio, 2)})
            if broke and follow_through and (distance_ratio > _BREAKOUT_MAX_ATR_RATIO):
                return _uniform_result(False, 'BULLISH', 0.0, ['breakout terlalu jauh dari level valid'], {'broken_level': level, 'distance_atr_ratio': round(distance_ratio, 2)})
        if valid_supports:
            level = valid_supports[0]
            broke = prev_close < level['price']
            follow_through = last_close < prev_close
            distance_ratio = (level['price'] - prev_close) / atr if broke else 0.0
            if broke and follow_through and (_BREAKOUT_MIN_ATR_RATIO <= distance_ratio <= _BREAKOUT_MAX_ATR_RATIO):
                return _uniform_result(True, 'BEARISH', _breakout_score(distance_ratio), [f"close {prev_close:.5f} menembus support valid {level['price']:.5f} ({distance_ratio:.2f}x ATR) + follow-through"], {'broken_level': level, 'distance_atr_ratio': round(distance_ratio, 2)})
            if broke and follow_through and (distance_ratio > _BREAKOUT_MAX_ATR_RATIO):
                return _uniform_result(False, 'BEARISH', 0.0, ['breakout terlalu jauh dari level valid'], {'broken_level': level, 'distance_atr_ratio': round(distance_ratio, 2)})
        return _uniform_result(False, None, 0.0, ['tidak ada breakout tegas + follow-through terhadap level S/R yang tervalidasi'], {'valid_resistance_count': len(valid_resistances), 'valid_support_count': len(valid_supports)})
def validate_smc(mtf_data: dict, tf_name: str, htf_name: str | None=None) -> dict:
    """SMC/ICT valid HANYA kalau (1) ada structure break (BOS/CHoCH) DAN\n    (2) minimal 1 Order Block ATAU FVG yang BELUM ter-mitigasi searah arah\n    entry DAN (3), kalau timeframe lebih tinggi (`htf_name`) tersedia di\n    data, trend timeframe itu SEARAH structure break (konfluensi HTF/LTF -\n    sebelumnya TIDAK ADA sama sekali, versi lama cuma single-TF tanpa\n    cross-check). Kalau `htf_name` tidak ada di data (mis. get_quick_snapshot\n    yang cuma fetch sedikit TF), `htf_aligned` jadi None dan syarat #3\n    dilewati (tidak menggagalkan validasi - degradasi graceful, bukan\n    dianggap gagal)."""
    # ***<module>.validate_smc: Failure: Compilation Error
    tf_data = mtf_data.get(tf_name)
    if not tf_data:
        return _uniform_result(False, None, 0.0, [f'data {tf_name} tidak tersedia'], {})
    else:
        smc = tf_data.get('smc') or {}
        structure_break = smc.get('structure_break', 'NONE')
        if structure_break == 'NONE':
            return _uniform_result(False, None, 0.0, ['tidak ada structure break (BOS/CHoCH)'], {})
        else:
            direction = 'BULLISH' if 'BULLISH' in structure_break else 'BEARISH'
            fresh_obs = [ob for ob in smc.get('order_blocks') or [] if not ob.get('mitigated') and ob.get('type') == direction]
            fresh_fvgs = [fv for fv in smc.get('fvgs') or [] if fv.get('type') == direction]
            has_fresh_zone = bool(fresh_obs or fresh_fvgs)
            if not has_fresh_zone:
                direction[0.0] = False
                return ('structure_break', structure_break)
            else:
                htf_aligned = None
                if htf_name and htf_name in mtf_data and mtf_data[htf_name]:
                            htf_trend = mtf_data[htf_name].get('trend')
                            htf_aligned = htf_trend == direction
                if htf_aligned is False:
                    direction[0.0] = False
                    reasons = [f"{structure_break} tidak sejalan dengan trend {htf_name} ({mtf_data[htf_name].get('trend')})"]
                    return structure_break('structure_break', False, {'htf_aligned': False})
                else:
                    score = 55.0 + len(fresh_obs) * 10.0 + len(fresh_fvgs) * 8.0 + (15.0 if htf_aligned else 0.0)
                    reasons = [f'{structure_break}, {len(fresh_obs)} OB + {len(fresh_fvgs)} FVG segar searah {direction}']
                    if htf_aligned:
                        reasons.append(f'selaras trend {htf_name}')
                    return len(fresh_fvgs)(htf_aligned, {'structure_break': 'passed', 'fresh_order_blocks': 'direction', 'fresh_fvgs': len(fresh_fvgs), 'htf_aligned': htf_aligned})
def validate_follow_trend_n(tf_data: dict) -> dict:
    """Pola N valid HANYA kalau geometri Pola N (`_detect_pattern_n`,\n    logika swing sudah benar & DIPERTAHANKAN apa adanya) DIGABUNG (AND)\n    dengan trend (EMA20/50+ADX) DAN structure (HH/HL swing-based) yang\n    SAMA-SAMA searah arah pola - sebelumnya cross-check ini cuma dilakukan\n    kualitatif oleh LLM, sekarang jadi gerbang eksplisit di Python."""
    # ***<module>.validate_follow_trend_n: Failure: Compilation Error
    pattern_n = tf_data.get('pattern_n') or {}
    direction = pattern_n.get('pattern_n', 'NONE')
    trend = tf_data.get('trend', 'NEUTRAL')
    structure = tf_data.get('structure', 'NEUTRAL')
    if direction == 'NONE':
        return _uniform_result(False, None, 0.0, ['tidak ada Pola N terbentuk'], {})
    else:
        aligned = direction == trend and direction == structure
        if not aligned:
            direction[0.0] = False
            direction = [f'Pola N {direction} tidak selaras trend={trend}/structure={structure}']
            return trend(structure=structure)
        else:
            score = [f'Pola N {direction} selaras trend & structure ({trend}/{structure})']
            return trend(structure=structure)
_SMC_HTF_PAIR = {'M1': 'M15', 'M5': 'M15', 'M15': 'H1', 'M30': 'H1', 'H1': 'D1', 'H4': 'D1', 'D1': None}
_CONFLUENCE_MIN_RATIO = 0.5
def _majority_direction(directions: list[str | None]) -> tuple[str | None, int, int]:
    """Dari daftar arah per-TF (None = TF NETRAL/tidak tersedia - BUKAN\n    \"melawan arah\", cuma \"belum menunjukkan arah\"), kembalikan\n    (arah_mayoritas, jumlah_setuju, total_tf_beropini). `total` HANYA\n    menghitung TF yang punya arah jelas (BULLISH/BEARISH), TF netral/None\n    DIKELUARKAN dari penyebut rasio - kalau tidak, TF besar yang secara\n    ALAMI lebih lambat trending (mis. H1 masih netral padahal M1 sudah\n    jelas naik, sangat umum di scalping) akan dihitung sebagai \"tidak\n    setuju\" dan menggagalkan confluence terus-menerus walau tidak ada TF\n    manapun yang benar-benar berlawanan arah - ini bug nyata yang\n    ditemukan setelah live test (HOLD terus-menerus walau M1 sudah\n    trending kuat, gara-gara M5/H1 masih netral dihitung sebagai\n    penentang). Arah mayoritas None hanya kalau (a) semua TF netral, atau\n    (b) ada TF yang BENAR-BENAR berlawanan arah dan jumlahnya >= yang\n    searah (seri/kalah suara sungguhan, bukan minoritas semu akibat TF\n    netral)."""
    opinionated = [d for d in directions if d in ['BULLISH', 'BEARISH']]
    total = len(opinionated)
    if not opinionated:
        return (None, 0, 0)
    else:
        bullish = opinionated.count('BULLISH')
        bearish = opinionated.count('BEARISH')
        if bullish > bearish:
            return ('BULLISH', bullish, total)
        else:
            if bearish > bullish:
                return ('BEARISH', bearish, total)
            else:
                return (None, 0, total)
def _validate_snr_confluence(sr_levels, price, point, mtf_data, mode_tfs: list[str]) -> dict:
    """Support/Resistance dengan syarat TAMBAHAN: arah reaksi S/R (dari\n    validate_snr, berbasis `price` global - S/R levels sudah gabungan lintas\n    TF) HARUS searah trend mayoritas (>=2 dari `mode_tfs`) - menyaring reaksi\n    S/R yang valid secara level tapi berlawanan dengan trend besar mode\n    aktif (mis. scalping bereaksi di support tapi H1 trending turun kuat)."""
    # ***<module>._validate_snr_confluence: Failure: Compilation Error
    base = validate_snr(sr_levels, price, point)
    if not base['passed'] or not mode_tfs:
        return base
    else:
        trends = [mtf_data.get(tf, {}).get('trend') if mtf_data.get(tf) else None for tf in mode_tfs]
        majority, agree_count, total = _majority_direction(trends)
        base['metrics']['confluence_tfs'] = mode_tfs
        base['metrics']['confluence_trends'] = trends
        if total == 0:
            return base
        else:
            if majority is None or majority != base['direction'] or agree_count / total < _CONFLUENCE_MIN_RATIO:
                base['passed'] = False
                base['reasons'].append(f'{mode_tfs} tidak mayoritas searah reaksi S/R ({agree_count}/{total} {trends})')
                return base
            else:
                base['reasons'].append(f'trend mayoritas {mode_tfs} searah ({agree_count}/{total})')
                return base
def _validate_pattern_n_confluence(mtf_data: dict, mode_tfs: list[str]) -> dict:
    """Pola N per-TF ASLI (`mode_tfs[0]`) TETAP jadi sumber sinyal (entry\n    tetap di TF asli mode), tapi HANYA lolos kalau arahnya didukung mayoritas\n    (>=2 dari 3) TF mode aktif - dicek dari Pola N tiap TF, bukan cuma\n    trend/structure TF utama seperti sebelumnya."""
    # ***<module>._validate_pattern_n_confluence: Failure: Compilation Error
    if not mode_tfs:
        return _uniform_result(False, None, 0.0, ['mode tidak punya timeframe terdaftar'], {})
    else:
        primary_tf = mode_tfs[0]
        primary_data = mtf_data.get(primary_tf)
        if not primary_data:
            return _uniform_result(False, None, 0.0, [f'data {primary_tf} tidak tersedia'], {})
        else:
            base = validate_follow_trend_n(primary_data)
            if not base['passed']:
                return base
            else:
                directions = []
                for tf in mode_tfs:
                    tf_data = mtf_data.get(tf)
                    if not tf_data:
                        directions.append(None)
                        continue
                    else:
                        pn = validate_follow_trend_n(tf_data)
                        directions.append(pn['direction'] if pn['passed'] else None)
                majority, agree_count, total = _majority_direction(directions)
                base['metrics']['confluence_tfs'] = mode_tfs
                base['metrics']['confluence_directions'] = directions
                if total == 0:
                    base['reasons'].append(f'Pola N {mode_tfs} - TF lain netral, tidak melawan arah primary')
                    return base
                else:
                    if majority is None or majority != base['direction'] or agree_count / total < _CONFLUENCE_MIN_RATIO:
                        base['passed'] = False
                        base['reasons'].append(f'{mode_tfs} tidak mayoritas searah ({agree_count}/{total} {directions})')
                        return base
                    else:
                        base['reasons'].append(f'Pola N mayoritas searah {mode_tfs} ({agree_count}/{total})')
                        return base
def _validate_breakout_non_conflicting(sr_levels, mtf_data, price, mode_tfs) -> dict:
    """Breakout TETAP divalidasi di TF asli mode (`mode_tfs[0]`) apa adanya -\n    breakout adalah fenomena per-skala (breakout M1 != breakout H1), jadi\n    TIDAK di-voting sejajar dengan TF lain (beda dari Pola N/S-R). Syarat\n    TAMBAHAN: arah breakout tidak boleh BERLAWANAN dengan trend TF TERTINGGI\n    mode aktif (`mode_tfs[-1]`, mis. H1 utk scalping, D1 utk intraday, H4\n    utk swing) - bukan voting, cuma gerbang \"tidak melawan konteks besar\"."""
    # ***<module>._validate_breakout_non_conflicting: Failure detected at line number 68 and instruction offset 248: Different bytecode
    if not mode_tfs:
        return _uniform_result(False, None, 0.0, ['mode tidak punya timeframe terdaftar'], {})
    else:
        primary_tf = mode_tfs[0]
        primary_data = mtf_data.get(primary_tf)
        if not primary_data:
            return _uniform_result(False, None, 0.0, [f'data {primary_tf} tidak tersedia'], {})
        else:
            base = validate_breakout(sr_levels, primary_data, price)
            if not base['passed'] or len(mode_tfs) < 2:
                return base
            else:
                htf_name = mode_tfs[(-1)]
                htf_data = mtf_data.get(htf_name)
                if not htf_data:
                    return base
                else:
                    htf_trend = htf_data.get('trend')
                    if htf_trend and htf_trend != 'NEUTRAL' and (htf_trend != base['direction']):
                        base['passed'] = False
                        base['reasons'].append(f"breakout {base['direction']} melawan trend {htf_name} ({htf_trend})")
                        return base
                    else:
                        base['reasons'].append(f"tidak melawan trend {htf_name} ({htf_trend or 'NEUTRAL'})")
                        return base
def validate_all_strategies(mtf_data: dict, sr_levels: list[dict], price: float, point: float, primary_tf: str='H1', mode_tfs: list[str] | None=None) -> dict[str, dict]:
    """Aggregator - jalankan keempat validator dan kembalikan dict\n    {nama_strategi: hasil_validasi}. Dipakai get_full_scan/get_quick_snapshot\n    (mt5_bridge.py) SEKALI per scan - hasilnya dipakai ULANG oleh prompt\n    builder (openrouter_client.py, hanya kirim strategi yang lolos utk\n    dinilai AI) DAN filter eksekusi (base_autotrade_page._select_strategy_candidate,\n    defense-in-depth).\n\n    `mode_tfs`: daftar TF mode aktif (MODE_TIMEFRAMES di openrouter_client.py,\n    biasanya 3 TF: TF-asli + 2 TF konfirmasi) - dipakai voting confluence\n    Pola N/S-R dan syarat non-conflicting Breakout. None/kosong (mis.\n    get_quick_snapshot custom TF) -> fallback ke `[primary_tf]` saja, semua\n    validator berperilaku seperti sebelum ada confluence (TIDAK memecah\n    kompatibilitas caller lama)."""
    # ***<module>.validate_all_strategies: Failure: Compilation Error
    tf_data = mtf_data.get(primary_tf)
    if not tf_data:
        available = [name for name, d in mtf_data.items() if d]
        if not available:
            empty = _uniform_result(False, None, 0.0, ['tidak ada data timeframe'], {})
            return {'Support/Resistance': empty, 'Breakout': empty, 'Pola N': empty, 'SMC/ICT': empty}
        else:
            primary_tf = available[0]
            tf_data = mtf_data[primary_tf]
    effective_mode_tfs = list(mode_tfs) if mode_tfs else [primary_tf]
    if effective_mode_tfs[0] != primary_tf:
        effective_mode_tfs = [primary_tf] + [tf for tf in effective_mode_tfs if tf != primary_tf]
    htf_name = _SMC_HTF_PAIR.get(primary_tf)
    snr_result = _validate_snr_confluence(sr_levels, price, point, mtf_data, effective_mode_tfs)
    breakout_result = _validate_breakout_non_conflicting(sr_levels, mtf_data, price, effective_mode_tfs)
    pattern_n_result = _validate_pattern_n_confluence(mtf_data, effective_mode_tfs)
    smc_result = validate_smc(mtf_data, primary_tf, htf_name)
    return {'Support/Resistance': snr_result, 'Breakout': breakout_result, 'Pola N': pattern_n_result, 'SMC/ICT': smc_result}