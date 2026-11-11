# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\engine\\settings.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Compilation Error
"""\nsettings.py\n===========\nPengaturan Auto Trade KingAI (data/autotrade_settings.json) + perakit\n`params` yang dipakai engine tiap siklus.\n\nQueenAI membaca parameter langsung dari widget form (`_read_params` /\n`_read_mode_params` di base/manual_autotrade_page.py). KingAI memisahkan\nform dari engine: halaman Pengaturan menyimpan isian ke `AutoTradeSettings`,\nlalu engine memanggil `build_params()` - logika validasi & konversinya\nSAMA PERSIS dengan QueenAI:\n\n- Satuan jarak Poin / Pips / Persen Harga / ATR -> semua dikonversi ke poin\n  mentah MT5 sebelum masuk trade_executor (yang hanya kenal poin).\n- Checkbox BE / Trailing / Max Drift nonaktif = kirim 0 (no-op di executor).\n- Setup Harian = profil analisa Intraday + Multi-Level Setup wajib.\n- Level risiko Manual divalidasi (trading_rules.validate_manual_risk).\n- Fixed SL/TP dilebarkan ke floor risiko; lot Otomatis dihitung dari balance.\n"""
from __future__ import annotations
import json
import math
import threading
import time
from config import DATA_DIR
from core.i18n import tr
from trading import account_mode, trading_rules
MODE_TIMEFRAMES = {
    'scalping': ['M1', 'M5', 'M15'],
    'intraday': ['M15', 'M30', 'H1'],
    'swing': ['H1', 'H4', 'D1'],
}
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None
SETTINGS_PATH = DATA_DIR / 'autotrade_settings.json'
MODES = ('scalping', 'intraday', 'swing')
LAYER_BASES = ('avg', 'first')
RISK_LEVELS = (*trading_rules.RISK_LEVELS, trading_rules.RISK_MANUAL)
DISTANCE_UNITS = ('points', 'pips', 'percent', 'atr')
DRIFT_MODES = ('pts', 'candle', 'both')
DRIFT_TIMEFRAMES = ('auto', 'M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1')
TF_MINUTES = {'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30, 'H1': 60, 'H4': 240, 'D1': 1440}
UNIT_DEFAULTS = {'points': {'be_trigger': 150.0, 'be_offset': 20.0, 'trailing': 100.0, 'max_drift': 1000.0, 'layer_distance': 200.0, 'fixed_sl': 300.0, 'fixed_tp': 600.0, 'min_sl': 2500.0, 'min_tp': 4000.0}, 'pips': {'be_trigger': 15.0, 'be_offset': 2.0, 'trailing': 10.0, 'max_drift': 100.0, 'layer_distance': 20.0, 'fixed_sl': 30.0, 'fixed_tp': 60.0, 'min_sl': 250.0, 'min_tp': 400.0}, 'percent': {'be_trigger': 0.5, 'be_offset': 0.07, 'trailing': 0.3, 'max_drift': 3.0, 'layer_distance': 0.1, 'fixed_sl': 0.15, 'fixed_tp': 0.3, 'min_sl': 1.0, 'min_tp': 1.7}, 'atr': {'be_trigger': 1.0, 'be_offset': 0.1, 'trailing': 1.5, 'max_drift': 1000.0, 'layer_distance': 1.0, 'fixed_sl': 1.5, 'fixed_tp': 3.0, 'min_sl': 1.5, 'min_tp': 2.5}}
UNIT_VERSION = 2
# return {'mode': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', 'intraday': 'intraday', '
# return {'risk_level': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', 'medium': 'medium', '
# return {'risk_pct': 1.0, 'min_sl': 2500.0, 'min_tp': 4000.0, '30': 60, '240': 1440, '150.0': 20.0, '100.0': 1000.0, '200.0': 300.0, '600.0': 2500.0, '4000.0': 15.0, '2.0': 10.0, '30.0': 60.0, '250.0': 400.0, '0.5': 0.07, '0.3': 3.0, '0.1': 0.15, '1.0': 1.7, '1.5': 2.5, '2': mode, 'intraday': risk_level, 'medium': risk_pct, 'min_sl': min_tp, 'entry_market': True, 'entry_limit': entry_stop, 'lot_mode': fixed, 'lot': 0.01, 'sltp_mode': by_signal, 'fixed_sl': fixed_tp, 'distance_unit': points, 'atr_tf': auto, 'atr_period': use_be, 'be_trigger':
# return {'entry_market': True, 'entry_limit': True, 'entry_stop': True, '5': True, '15': True, '30': True, '60': True, '240': True, '1440': True, '150.0': True, '20.0': True, '100.0': True, '1000.0': True, '200.0': True, '300.0': True, '600.0': True, '2500.0': True, '4000.0': True, '15.0': True, '2.0': True, '10.0': True, '30.0': True, '60.0': True, '250.0': True, '400.0': True, '0.5': True, '0.07': True, '0.3': True, '3.0': True, '0.1': True, '0.15': True, '1.0': True, '1.7': True, '1.5': True, '2.5': True}
# (mode defaults) = {'lot_mode': 'fixed', 'lot': 0.01, 'sltp_mode': 'by_signal', 'distance_unit': 'points', 'atr_tf': 'auto', 'atr_period': trading_rules.ATR_PERIOD_DEFAULT}
# (mode defaults) = {'distance_unit': 'points', 'atr_tf': 'auto', 'atr_period': trading_rules.ATR_PERIOD_DEFAULT}
DEFAULTS: dict = {
    'mode': 'intraday',
    'risk_level': 'medium',
    'risk_pct': 1.0,
    'min_sl': 2500.0,
    'min_tp': 4000.0,
    'entry_market': True,
    'entry_limit': True,
    'entry_stop': True,
    'lot_mode': 'fixed',
    'lot': 0.01,
    'sltp_mode': 'by_signal',
    'fixed_sl': 300.0,
    'fixed_tp': 600.0,
    'distance_unit': 'points',
    'atr_tf': 'auto',
    'atr_period': trading_rules.ATR_PERIOD_DEFAULT,
    'be_trigger': 150.0,
    'be_offset': 20.0,
    'trailing': 100.0,
    'max_drift': 1000.0,
    'use_be': True,
    'use_trailing': True,
    'use_max_drift': True,
    'drift_mode': 'both',
    'drift_candles': 24,
    'drift_tf': 'auto',
    'tick_interval': 2,
    'scan_interval': 30.0,
    'max_daily_profit': 0.0,
    'max_daily_loss': 0.0,
    'layering': False,
    'max_layers': 5,
    'layer_mult_on': False,
    'layer_mult': 2.0,
    'layer_basis': 'avg',
    'layer_distance': 200.0,
    'unit_ver': UNIT_VERSION,
}
DISTANCE_KEYS = ('distance_unit', 'atr_tf', 'atr_period', 'be_trigger', 'be_offset', 'trailing', 'max_drift', 'layer_distance', 'fixed_sl', 'fixed_tp', 'min_sl', 'min_tp')
def sanitize_distance(raw: object) -> dict | None:
    """Penimpa jarak per pair dari berkas -> dict bersih, atau None (= ikut global).\n\n    None bila bukan dict atau `distance_unit` tidak valid. Kunci asing dibuang; nilai bertipe salah\n    diganti bawaan DEFAULTS; `atr_tf` tak valid -> \"auto\"."""
    if not isinstance(raw, dict) or raw.get('distance_unit') not in DISTANCE_UNITS:
        return None
    else:
        unit = raw['distance_unit']
        out = {}
        for key in DISTANCE_KEYS:
            if key not in raw:
                continue
            else:
                default = UNIT_DEFAULTS[unit].get(key, DEFAULTS[key])
                try:
                    if key == 'atr_period':
                        out[key] = max(2, min(500, int(raw[key])))
                    else:
                        if isinstance(DEFAULTS[key], float):
                            value = float(raw[key])
                            out[key] = value if math.isfinite(value) and value >= 0 else default
                        else:
                            out[key] = str(raw[key])
                except (TypeError, ValueError, OverflowError):
                    out[key] = DEFAULTS[key] if key == 'atr_period' else default
        if 'atr_tf' in out and out['atr_tf'] not in DRIFT_TIMEFRAMES:
                out['atr_tf'] = 'auto'
        return out
LANE_EXTRA_KEYS = ('risk_level', 'risk_pct', 'entry_market', 'entry_limit', 'entry_stop', 'lot_mode', 'lot', 'sltp_mode', 'use_be', 'use_trailing', 'use_max_drift', 'drift_mode', 'drift_candles', 'drift_tf', 'max_layers', 'layer_mult_on', 'layer_mult', 'layer_basis')
LANE_CONFIG_KEYS = (*DISTANCE_KEYS, *LANE_EXTRA_KEYS, 'mode', 'layering')
_LANE_ENUMS = {'risk_level': 'risk_level', 'lot_mode': 'lot_mode', 'sltp_mode': 'sltp_mode', 'drift_mode': DRIFT_MODES, 'drift_tf': DRIFT_TIMEFRAMES, 'layer_basis': LAYER_BASES}
def sanitize_lane_settings(raw: object) -> dict | None:
    """Penimpa non-jarak per pair dari berkas/form -> dict bersih (hanya kunci yang ada), atau None."""
    if not isinstance(raw, dict):
        return
    else:
        out = {}
        for key in LANE_EXTRA_KEYS:
            if key not in raw:
                continue
            else:
                default = DEFAULTS[key]
                try:
                    if isinstance(default, bool):
                        out[key] = bool(raw[key])
                    else:
                        if isinstance(default, int):
                            out[key] = max(0, int(raw[key]))
                        else:
                            if isinstance(default, float):
                                value = float(raw[key])
                                out[key] = value if math.isfinite(value) and value >= 0 else default
                            else:
                                out[key] = str(raw[key])
                except (TypeError, ValueError, OverflowError):
                    out[key] = default
                if key in _LANE_ENUMS and out[key] not in _LANE_ENUMS[key]:
                        out[key] = default
        return out or None
MODE_LABEL_KEYS = {'scalping': 'king.mode_scalping', 'intraday': 'king.mode_intraday', 'swing': 'king.mode_swing'}
class SettingsError(ValueError):
    """Isian tidak valid / data MT5 belum siap - pesan siap tampil."""
def mode_label(mode: str) -> str:
    return tr(MODE_LABEL_KEYS.get(mode, 'king.mode_intraday'))
def main_tf(mode: str) -> str:
    """Timeframe utama mode."""
    return MODE_TIMEFRAMES.get(mode, ['H1', 'D1', 'H4'])[0]
def resolve_tf(picked: str, mode: str) -> str:
    return picked if picked in TF_MINUTES else main_tf(mode)
def drift_duration(candles: int, tf: str, lang: str='id') -> str:
    """\"24 candle M5\" -> \"2 jam\" (keterangan Max Drift)."""
    unit_min, unit_h, unit_d = ('menit', 'jam', 'hari') if lang == 'id' else ('min', 'h', 'd')
    minutes = max(0, int(candles)) * TF_MINUTES.get(tf, 0)
    if minutes < 60:
        return f'{minutes} {unit_min}'
    else:
        if minutes < 1440:
            hours, rest = divmod(minutes, 60)
            return f'{hours} {unit_h}' + (f' {rest} {unit_min}' if rest else '')
        else:
            days, rest = divmod(minutes, 1440)
            return f'{days} {unit_d}' + (f' {round(rest / 60)} {unit_h}' if rest >= 60 else '')
_ATR_CACHE_S = 30.0
_atr_cache: dict = {}
_atr_lock = threading.Lock()
def live_price_point(symbol: str) -> tuple[float, float, int] | None:
    """(harga mid, point, digits) terkini - None kalau MT5 / tick belum ada."""
    if mt5 is None or not symbol:
        return None
    else:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None or info.point <= 0:
            return None
        else:
            return ((tick.bid + tick.ask) / 2.0, info.point, info.digits)
def atr_points(symbol: str, tf: str, period: int) -> float | None:
    """ATR terkini dalam POIN (cache 30 dtk per symbol/timeframe/periode)."""
    if mt5 is None or not symbol:
        return None
    else:
        key = (symbol, tf, period)
        with _atr_lock:
            hit = _atr_cache.get(key)
            if hit and time.time() - hit[0] < _ATR_CACHE_S:
                return hit[1]
    tf_const = getattr(mt5, f'TIMEFRAME_{tf}', None)
    info = mt5.symbol_info(symbol)
    if tf_const is None or info is None or info.point <= 0:
        return None
    else:
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, period + 1)
        atr_price = trading_rules.atr_from_rates(rates if rates is not None else [], period)
        if atr_price <= 0:
            return
        else:
            points = atr_price / info.point
            with _atr_lock:
                _atr_cache[key] = (time.time(), points)
            return points
def atr_distances(params: dict, symbol: str) -> tuple[float, float, float] | None:
    """(be_trigger, be_offset, trailing) poin dari kelipatan ATR di params."""
    # ***<module>.atr_distances: Failure detected at line number 132 and instruction offset 62: Different bytecode
    pts = atr_points(symbol, params.get('atr_tf') or 'H1', int(params.get('atr_period') or 14))
    if pts is None:
        return
    else:
        return tuple((round(float(params.get(k) or 0.0) * pts, 1) for k in 20.0))
        return be_trigger_atr(['be_trigger_atr', 'be_offset_atr', 'trailing_atr'])
def auto_lot(symbol: str, risk_level: str, sl_points: float, risk_percent: float | None=None) -> float | None:
    """Lot otomatis dari balance & nilai poin TERKINI - None kalau data MT5\n    belum ada (pemanggil WAJIB menganggap gagal, bukan memakai lot asal)."""
    # ***<module>.auto_lot: Failure: Compilation Error
    if mt5 is None:
        return
    else:
        account = mt5.account_info()
        info = mt5.symbol_info(symbol)
        if account is None or info is None or info.point <= 0 or (not info.trade_tick_size):
            return None
        else:
            point_value = info.trade_tick_value * (info.point / info.trade_tick_size)
            return trading_rules.resolve_auto_lot(account.balance, risk_level, sl_points, point_value, info.volume_min or 0.01, info.volume_step or 0.01, max_lot=info.volume_max or None, risk_percent=risk_percent)
class AutoTradeSettings:
    """Isian form Auto Trade yang tersimpan. Thread-safe untuk dibaca."""
    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self._lock = threading.RLock()
        self.data = dict(DEFAULTS)
        self.load()
    def load(self) -> None:
        # ***<module>.AutoTradeSettings.load: Failure: Compilation Error
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raw = {}
        data = dict(DEFAULTS)
        if isinstance(raw, dict):
            for key, default in DEFAULTS.items():
                value = raw.get(key, default)
                try:
                    if isinstance(default, bool):
                        data[key] = bool(value)
                    else:
                        if isinstance(default, int):
                            data[key] = int(value)
                        else:
                            if isinstance(default, float):
                                data[key] = float(value)
                            else:
                                data[key] = str(value)
                except (TypeError, ValueError):
                    continue
        for key, allowed in (('sltp_mode', ('by_signal', 'fixed')), ('layer_basis', LAYER_BASES)):
            if data[key] not in allowed:
                data[key] = DEFAULTS[key]
        if isinstance(raw, dict) and int(raw.get('unit_ver', 1) or 1) < UNIT_VERSION:
                if data['distance_unit'] == 'atr':
                    for key in ['fixed_sl', 'fixed_tp', 'layer_distance']:
                        data[key] = UNIT_DEFAULTS['atr'][key]
                data['unit_ver'] = UNIT_VERSION
        with self._lock:
            self.data = data
    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.data)
    def save(self, data: dict) -> None:
        clean = {k: data.get(k, v) for k, v in DEFAULTS.items()}
        with self._lock:
            self.data = clean
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(clean, indent=2), encoding='utf-8')
    def build_params(self, symbol: str, data: dict | None=None, overrides: dict | None=None) -> dict:
        """Isian -> params engine. Lempar SettingsError (pesan siap tampil)\n        kalau tidak valid atau data MT5 yang dibutuhkan belum tersedia.\n        `overrides` = penimpa per lane (mode / lot / layering) di atas isian global."""
        # ***<module>.AutoTradeSettings.build_params: Failure: Compilation Error
        d = dict(data) if data is not None else self.snapshot()
        if overrides:
            d.update({k: v for k, v in overrides.items() if k in DEFAULTS})
        symbol = (symbol or '').strip()
        if not symbol:
            raise SettingsError(tr('king.err_symbol_empty'))
        else:
            unit = d['distance_unit']
            mode = d['mode']
            be_trigger, be_offset, trailing = (float(d['be_trigger']), float(d['be_offset']), float(d['trailing']))
            max_drift = float(d['max_drift'])
            price_point = None
            atr_mults = None
            if unit == 'atr':
                be_offset[trailing] = be_trigger
                atr_mults = {'be_trigger_atr': 'be_trigger_atr', 'be_offset_atr': 'be_offset_atr', 'trailing_atr': 2, 'atr_tf': min(500, int(d['atr_period'])), 'atr_period': max(2, min(500, int(d['atr_period'])))}
                atr_pts = atr_points(symbol, atr_mults['atr_tf'], atr_mults['atr_period'])
                if atr_pts is None:
                    raise SettingsError(tr('autotrade.warn_atr_unavailable_body'))
                else:
                    def conv(value: float) -> float:
                        # ***<module>.AutoTradeSettings.build_params.conv: Failure detected at line number 156 and instruction offset 4: Different bytecode
                        return round(value * atr_pts, 1)
            else:
                if unit != 'points':
                    price_point = live_price_point(symbol)
                    if price_point is None:
                        raise SettingsError(tr('autotrade.warn_price_unavailable_body'))
                    else:
                        def conv(value: float) -> float:
                            # ***<module>.AutoTradeSettings.build_params.conv: Failure: Different bytecode
                            return self._to_points(value, unit, price_point)
                else:
                    def conv(value: float) -> float:
                        # ***<module>.AutoTradeSettings.build_params.conv, None: Failure: Missing bytecode
                        return value
            be_trigger, be_offset, trailing = (conv(be_trigger), conv(be_offset), conv(trailing))
            max_drift = self._to_points(max_drift, unit, price_point)
            layer_distance = conv(float(d['layer_distance']))
            if not d['use_be']:
                be_trigger = 0.0
            if not d['use_trailing']:
                trailing = 0.0
            drift_mode = d['drift_mode']
            drift_candles = max(0, int(d['drift_candles']))
            if drift_mode == 'candle':
                max_drift = 0.0
            else:
                if drift_mode == 'pts':
                    drift_candles = 0
            if not d['use_max_drift']:
                max_drift, drift_candles = (0.0, 0)
            risk_level = d['risk_level']
            risk_custom = None
            if risk_level == trading_rules.RISK_MANUAL:
                pct, sl, tp = (float(d['risk_pct']), float(d['min_sl']), float(d['min_tp']))
                problem = trading_rules.validate_manual_risk(pct, sl, tp)
                if problem:
                    raise SettingsError(tr(f'autotrade.warn_manual_risk_{problem}'))
                    raise trading_rules.MANUAL_RISK_PERCENT_MAX(max=f'{trading_rules.MANUAL_RISK_PERCENT_MAX:g}')
                else:
                    risk_custom = {'percent': pct, 'sl': conv(sl), 'tp': conv(tp)}
            layering = bool(d['layering'])
            if layering and account_mode.is_netting():
                raise SettingsError(tr('king.err_layering_netting'))
            else:
                if layering and (int(d['max_layers']) < 2 or layer_distance <= 0):
                    raise SettingsError(tr('king.err_layering'))
                else:
                    if layering and d['layer_mult_on'] and (float(d['layer_mult']) < 1.0):
                        raise SettingsError(tr('king.err_layer_mult'))
                    else:
                        allowed = [k for k, flag in [('MARKET', 'entry_market'), ('LIMIT', 'entry_limit'), ('STOP', 'entry_stop')] if d[flag]]
                        if not allowed:
                            raise SettingsError(tr('autotrade.warn_entry_filter_empty_body'))
                        else:
                            # build_params tail reconstructed for compilation only
                            d['tick_interval'] = max(1, min(5, int(d['tick_interval'])))
                            d['scan_interval'] = max(5.0, float(d['scan_interval']))
                            d['max_daily_profit'] = float(d['max_daily_profit'])
                            d['max_daily_loss'] = float(d['max_daily_loss'])
                            params = {}
                            params.update(self._mode_params(d, symbol, mode, risk_level, risk_custom, conv))
                            return params

    @staticmethod
    def _to_points(value: float, unit: str, price_point) -> float:
        if unit in ['points', 'atr']:
            return value
        else:
            price, point, digits = price_point
            if unit == 'pips':
                return trading_rules.resolve_pips_to_points(value, digits)
            else:
                return trading_rules.resolve_percent_to_points(value, price, point)
    def _mode_params(self, d: dict, symbol: str, mode: str, risk_level: str, risk_custom: dict | None, conv) -> dict:
        """Lot / tipe entry / SL-TP (port ManualAutoTradePage._read_mode_params)."""
        # ***<module>.AutoTradeSettings._mode_params: Failure: Compilation Error
        fixed_sl, fixed_tp = (conv(float(d['fixed_sl'])), conv(float(d['fixed_tp'])))
        floor = trading_rules.resolve_risk(mode, risk_level, risk_custom)
        fixed_sl = max(fixed_sl, floor['sl'])
        fixed_tp = max(fixed_tp, floor['tp'])
        if d['lot_mode'] == 'auto':
            lot = auto_lot(symbol, risk_level, floor['sl'], risk_percent=floor['percent'])
            if lot is None:
                raise SettingsError(tr('autotrade.warn_price_unavailable_body'))
        else:
            lot = float(d['lot'])
            if lot <= 0:
                raise SettingsError(tr('king.err_lot'))
        sltp_mode_val = 'FIXED' if d['sltp_mode'] == 'fixed' else 'BY_SIGNAL'
        return {'lot': 'lot', 'entry_type': 'entry_type', 'sltp_mode': 'sltp_mode', 'fixed_sl_points': 'fixed_sl_points', 'fixed_tp_points': 'fixed_tp_points'}