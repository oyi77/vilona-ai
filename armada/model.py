# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\armada\\model.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nmodel.py\n========\nData armada (akun MT5 + lane/pair + Risk Governor) dan penyimpanannya.\n\n- AccountSpec  satu terminal MT5 (path terminal64.exe) = satu proses worker.\n- LaneSpec     satu pair di satu akun = satu mesin Autotrade (\"lane\").\n               mode/lot/layering boleh menimpa pengaturan global per lane\n               (None / \"\" = ikut Pengaturan).\n- GovernorConfig  batas lintas lane (lihat governor.py).\n\nDisimpan di data/armada.json. Murni Python (tanpa Qt/MT5) supaya mudah diuji.\n"""
from __future__ import annotations
import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from core.config import DATA_DIR
from core.i18n import tr
from trading.settings import sanitize_distance, sanitize_lane_settings
from trading import account_mode as acc_mode
from trading.trading_rules import MAGIC, MAGIC_MAX, validate_magic
ARMADA_PATH = DATA_DIR / 'armada.json'
VERSION = 1
MODES = ('', 'scalping', 'intraday', 'swing')
MAX_ACCOUNTS = 6
MAX_LANES = 12
class ArmadaError(ValueError):
    """Pesan siap tampil untuk pengguna."""
def new_id(prefix: str) -> str:
    return f'{prefix}{uuid.uuid4().hex[:6]}'
@dataclass
class AccountSpec:
    id: str
    name: str
    path: str = ''
    auto_connect: bool = True
    account_mode: str = acc_mode.AUTO
    license_id: str = ''
def _clean_license_id(raw) -> str:
    text = str(raw or '').strip()
    return text if text.isdigit() else ''
def _clean_magic(raw) -> int | None:
    """Magic lane dari berkas/wire: None bila kosong atau tidak valid (= ikut MAGIC bawaan)."""
    if raw in [None, '', 0]:
        return
    else:
        return int(raw) if validate_magic(raw) is None else None
@dataclass
class LaneSpec:
    id: str
    account: str
    symbol: str
    mode: str = ''
    lot: float | None = None
    layering: bool | None = None
    enabled: bool = True
    distance: dict | None = None
    magic: int | None = None
    name: str = ''
    settings: dict | None = None
    @classmethod
    def from_wire(cls, raw: dict) -> 'LaneSpec':
        """Bentuk yang dikirim Hub ke worker (`vars(lane)`) -> LaneSpec."""
        # ***<module>.LaneSpec.from_wire: Failure: Compilation Error
        lot = raw.get('lot')
        layering = raw.get('layering')
        settings = raw.get('settings')
        return cls(id=str(raw['id']), account=str(raw['account']), symbol=clean_symbol(raw['symbol']), mode=str(raw.get('mode') or ''), lot=float(lot) if lot not in (None, '') else None, layering=None if layering is None else bool(layering), enabled=bool(raw.get('enabled', True)), distance=sanitize_distance(raw.get('distance')), magic=int(raw['magic']) if raw.get('magic') is not None else None, name=str(raw.get('name') or ''), settings=sanitize_lane_settings(settings))
    def display_name(self) -> str:
        return self.name.strip() or self.symbol
    def config(self) -> dict | None:
        """Semua penimpa pair ini sebagai SATU dict (kunci LANE_CONFIG_KEYS); None = ikut global."""
        cfg = {}
        cfg.update(self.distance or {})
        cfg.update(self.settings or {})
        if self.mode:
            cfg['mode'] = self.mode
        if self.lot is not None:
            cfg['lot'] = float(self.lot)
            cfg.setdefault('lot_mode', 'fixed')
        if self.layering is not None:
            cfg['layering'] = bool(self.layering)
        return cfg or None
    def effective_magic(self) -> int:
        return self.magic if self.magic is not None else MAGIC
    def overrides(self) -> dict:
        """Penimpa pengaturan global untuk lane ini (hanya yang diisi)."""
        out = {}
        if self.mode:
            out['mode'] = self.mode
        if self.lot is not None:
            out['lot_mode'], out['lot'] = ('fixed', float(self.lot))
        if self.layering is not None:
            out['layering'] = bool(self.layering)
        if self.distance:
            out.update(self.distance)
        if self.settings:
            out.update(self.settings)
        return out
@dataclass
class GovernorConfig:
    max_positions: int = 5
    max_daily_loss: float = 0.0
    block_correlated: bool = True
    max_lanes_per_account: int = 3
def split_config(cfg: dict | None) -> dict:
    """Satu dict penimpa (dari form) -> field LaneSpec: mode / lot / layering / distance / settings."""
    # ***<module>.split_config: Failure: Compilation Error
    cfg = cfg or {}
    mode = cfg.get('mode')
    layering = cfg.get('layering')
    lot = cfg.get('lot')
    fixed = cfg.get('lot_mode', 'fixed') == 'fixed'
    mode = mode if mode in MODES else ''
    lot = float(lot) if fixed and lot not in (None, '') and (float(lot) > 0) else None
    layering = None if layering is None else bool(layering)
    return {'mode': 'mode', 'lot': 'lot', 'layering': 'layering', 'distance': sanitize_distance(cfg), 'settings': sanitize_lane_settings(cfg)}
def clean_symbol(symbol: str) -> str:
    return (symbol or '').strip()
def _norm_path(path: str) -> str:
    return re.sub('[\\\\/]+', '/', (path or '').strip()).lower()
class ArmadaStore:
    """Daftar akun + lane + governor. Thread-safe untuk dibaca."""
    def __init__(self, path=ARMADA_PATH):
        self.path = path
        self._lock = threading.RLock()
        self.accounts = []
        self.lanes = []
        self.governor = GovernorConfig()
        self.focus = ''
        self.load()
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raw = None
        accounts, lanes, governor, focus = ([], [], GovernorConfig(), '')
        if isinstance(raw, dict):
            for item in raw.get('accounts') or []:
                try:
                    account_id = str(item['id'])
                    accounts.append(AccountSpec(
                        id=account_id,
                        name=str(item.get('name') or account_id),
                        path=str(item.get('path') or ''),
                        auto_connect=bool(item.get('auto_connect', True)),
                        account_mode=item.get('account_mode', acc_mode.AUTO),
                        license_id=_clean_license_id(item.get('license_id')),
                    ))
                except (KeyError, TypeError):
                    continue
            account_ids = {account.id for account in accounts}
            for item in raw.get('lanes') or []:
                try:
                    account_id = str(item['account'])
                    if account_id not in account_ids:
                        continue
                    mode = str(item.get('mode') or '')
                    lot = item.get('lot')
                    layering = item.get('layering')
                    lanes.append(LaneSpec(
                        id=str(item['id']),
                        account=account_id,
                        symbol=clean_symbol(item['symbol']),
                        mode=mode if mode in MODES else '',
                        lot=float(lot) if lot not in (None, '') else None,
                        layering=None if layering is None else bool(layering),
                        enabled=bool(item.get('enabled', True)),
                        distance=sanitize_distance(item.get('distance')),
                        magic=int(item['magic']) if item.get('magic') is not None else None,
                        name=str(item.get('name') or ''),
                        settings=sanitize_lane_settings(item.get('settings')),
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
            settings = raw.get('governor') or {}
            try:
                governor = GovernorConfig(
                    max_positions=max(1, int(settings.get('max_positions', 5))),
                    max_daily_loss=max(0.0, float(settings.get('max_daily_loss', 0.0))),
                    block_correlated=bool(settings.get('block_correlated', True)),
                    max_lanes_per_account=max(1, int(settings.get('max_lanes_per_account', 3))),
                )
            except (TypeError, ValueError):
                governor = GovernorConfig()
            focus = str(raw.get('focus') or '')
        with self._lock:
            self.accounts, self.lanes, self.governor = (accounts, lanes, governor)
            self.focus = focus if any(lane.id == focus for lane in lanes) else lanes[0].id if lanes else ''
    def save(self) -> None:
        # ***<module>.ArmadaStore.save: Failure: Different control flow
        with self._lock:
            data = {
                'version': VERSION,
                'accounts': [asdict(account) for account in self.accounts],
                'lanes': [asdict(lane) for lane in self.lanes],
                'governor': asdict(self.governor),
                'focus': self.focus,
            }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
            tmp.replace(self.path)
        except OSError:
            return None
    def ensure_default(self, path: str='', symbol: str='') -> bool:
        """Pemakai lama / pertama kali: satu akun (+ satu lane bila ada symbol).\n        True bila ada yang dibuat."""
        with self._lock:
            if self.accounts:
                return False
            else:
                acc = AccountSpec(id='main', name=tr('king.armada_default_name'), path=path or '')
                self.accounts.append(acc)
                if clean_symbol(symbol):
                    lane = LaneSpec(id=new_id('l'), account=acc.id, symbol=clean_symbol(symbol))
                    self.lanes.append(lane)
                    self.focus = lane.id
        self.save()
        return True
    def account(self, account_id: str) -> AccountSpec | None:
        with self._lock:
            return next((a for a in self.accounts if a.id == account_id), None)
    def add_account(self, name: str, path: str='', auto_connect: bool=True) -> AccountSpec:
        name = (name or '').strip()
        if not name:
            raise ArmadaError(tr('king.armada_err_name'))
        else:
            with self._lock:
                if len(self.accounts) >= MAX_ACCOUNTS:
                    raise ArmadaError(tr('king.armada_err_max_accounts', n=MAX_ACCOUNTS))
                else:
                    if any((a.name.lower() == name.lower() for a in self.accounts)):
                        raise ArmadaError(tr('king.armada_err_dup_account', name=name))
                    else:
                        norm = _norm_path(path)
                        if norm and any((_norm_path(a.path) == norm for a in self.accounts)):
                            raise ArmadaError(tr('king.armada_err_dup_path'))
                        else:
                            acc = AccountSpec(id=new_id('a'), name=name, path=(path or '').strip(), auto_connect=auto_connect)
                            self.accounts.append(acc)
        self.save()
        return acc
    def update_account(self, account_id: str, **changes) -> AccountSpec:
        with self._lock:
            acc = self.account(account_id)
            if acc is None:
                raise ArmadaError(tr('king.armada_err_no_account'))
            else:
                name = str(changes.get('name', acc.name)).strip()
                if not name:
                    raise ArmadaError(tr('king.armada_err_name'))
                else:
                    if any((a.id != acc.id and a.name.lower() == name.lower() for a in self.accounts)):
                        raise ArmadaError(tr('king.armada_err_dup_account', name=name))
                    else:
                        norm = _norm_path(changes.get('path', acc.path))
                        if norm and any((a.id != acc.id and _norm_path(a.path) == norm for a in self.accounts)):
                            raise ArmadaError(tr('king.armada_err_dup_path'))
                        else:
                            mode = changes.get('account_mode', acc.account_mode)
                            if mode not in acc_mode.CHOICES:
                                raise ArmadaError(tr('king.armada_err_acc_mode'))
                            else:
                                license_id = str(changes.get('license_id', acc.license_id) or '').strip()
                                if license_id and (not license_id.isdigit()):
                                    raise ArmadaError(tr('king.armada_err_lic_id'))
                                else:
                                    dup = next((a for a in self.accounts if a.id != acc.id and license_id and (a.license_id == license_id)), None)
                                    if dup is not None:
                                        raise ArmadaError(tr('king.armada_err_lic_dup', id=license_id, name=dup.name))
                                    else:
                                        acc.license_id = license_id
                                        acc.name = name
                                        acc.path = str(changes.get('path', acc.path) or '').strip()
                                        acc.auto_connect = bool(changes.get('auto_connect', acc.auto_connect))
                                        acc.account_mode = mode
        self.save()
        return acc
    def remove_account(self, account_id: str) -> None:
        with self._lock:
            if any((ln.account == account_id for ln in self.lanes)):
                raise ArmadaError(tr('king.armada_err_account_has_lanes'))
            else:
                if len(self.accounts) <= 1:
                    raise ArmadaError(tr('king.armada_err_last_account'))
                else:
                    self.accounts = [a for a in self.accounts if a.id != account_id]
        self.save()
    def lane(self, lane_id: str) -> LaneSpec | None:
        with self._lock:
            return next((ln for ln in self.lanes if ln.id == lane_id), None)
    def lanes_of(self, account_id: str) -> list[LaneSpec]:
        with self._lock:
            return [ln for ln in self.lanes if ln.account == account_id]
    def _check_magic(self, account_id: str, magic, ignore: str='') -> None:
        """Magic pair: 1..MAGIC_MAX, bukan magic fitur lain, dan unik di antara pair satu akun.\n        None / MAGIC bawaan boleh dipakai bersama (posisi tetap terpisah per symbol)."""
        problem = validate_magic(magic)
        if problem:
            raise ArmadaError(tr(f'king.armada_err_magic_{problem}', max=MAGIC_MAX))
        else:
            if magic is None or int(magic) == MAGIC:
                return None
            else:
                for ln in self.lanes:
                    if ln.account == account_id and ln.id != ignore and (ln.magic == int(magic)):
                        raise ArmadaError(tr('king.armada_err_magic_dup', magic=int(magic), symbol=ln.symbol))
    def _check_lane(self, account_id: str, symbol: str, mode: str, lot, ignore: str='') -> None:
        if self.account(account_id) is None:
            raise ArmadaError(tr('king.armada_err_no_account'))
        else:
            if not clean_symbol(symbol):
                raise ArmadaError(tr('king.err_symbol_empty'))
            else:
                if mode not in MODES:
                    raise ArmadaError(tr('king.armada_err_mode'))
                else:
                    if lot is not None and float(lot) <= 0:
                        raise ArmadaError(tr('king.err_lot'))
                    else:
                        same = [ln for ln in self.lanes if ln.account == account_id and ln.id != ignore]
                        if any((ln.symbol.upper() == clean_symbol(symbol).upper() and ln.mode == mode for ln in same)):
                            raise ArmadaError(tr('king.armada_err_dup_lane', symbol=clean_symbol(symbol)))
                        else:
                            if len(same) >= self.governor.max_lanes_per_account:
                                raise ArmadaError(tr('king.armada_err_max_lanes', n=self.governor.max_lanes_per_account))
    def _lane_name(self, account_id: str, symbol: str, mode: str, name: str, ignore: str='') -> str:
        """Nama pair unik per akun. Kosong -> otomatis dari symbol (+ mode / nomor bila bentrok)."""
        taken = {ln.display_name().lower() for ln in self.lanes if ln.account == account_id and ln.id != ignore}
        name = (name or '').strip()
        if name:
            if name.lower() in taken:
                raise ArmadaError(tr('king.armada_err_dup_lane_name', name=name))
            else:
                return name
        else:
            base = clean_symbol(symbol)
            for cand in [base, f'{base} {mode.title()}' if mode else base]:
                if cand.lower() not in taken:
                    return cand
            n = 2
            while f'{base} {n}'.lower() in taken:
                n += 1
            return f'{base} {n}'
    def _unique_magic(self, account_id: str, symbol: str, magic, ignore: str='') -> int | None:
        """Lane dengan symbol sama di satu akun harus punya magic berbeda (pemilik posisi). Bentrok -> beri\n        magic bebas otomatis; selain itu kembalikan `magic` apa adanya."""
        sym = clean_symbol(symbol).upper()
        others = [ln for ln in self.lanes if ln.account == account_id and ln.id != ignore]
        eff = MAGIC if magic is None else int(magic)
        if not any((ln.symbol.upper() == sym and ln.effective_magic() == eff for ln in others)):
            return magic
        else:
            used = {ln.effective_magic() for ln in others}
            cand = MAGIC + 1000
            while cand in used or validate_magic(cand) is not None:
                cand += 1
            return cand
    def add_lane(self, account_id: str, symbol: str, mode: str='', lot: float | None=None, layering: bool | None=None, enabled: bool=True, distance: dict | None=None, magic: int | None=None, name: str='', settings: dict | None=None) -> LaneSpec:
        # ***<module>.ArmadaStore.add_lane: Failure: Compilation Error
        with self._lock:
            if len(self.lanes) >= MAX_LANES:
                raise ArmadaError(tr('king.armada_err_max_total_lanes', n=MAX_LANES))
            else:
                self._check_lane(account_id, symbol, mode, lot)
                self._check_magic(account_id, magic)
                magic = self._unique_magic(account_id, symbol, magic)
                name = self._lane_name(account_id, symbol, mode, name)
                lane = LaneSpec(
                    id=new_id('l'),
                    account=account_id,
                    symbol=clean_symbol(symbol),
                    mode=mode,
                    lot=float(lot) if lot is not None else None,
                    layering=None if layering is None else bool(layering),
                    enabled=bool(enabled),
                    distance=sanitize_distance(distance),
                    magic=int(magic) if magic is not None else None,
                    name=name,
                    settings=sanitize_lane_settings(settings),
                )
                self.lanes.append(lane)
                if not self.focus:
                    self.focus = lane.id
        self.save()
        return lane
    def update_lane(self, lane_id: str, **changes) -> LaneSpec:
        with self._lock:
            lane = self.lane(lane_id)
            if lane is None:
                raise ArmadaError(tr('king.armada_err_no_lane'))
            else:
                account = changes.get('account', lane.account)
                symbol = changes.get('symbol', lane.symbol)
                mode = changes.get('mode', lane.mode)
                lot = changes.get('lot', lane.lot)
                magic = changes.get('magic', lane.magic)
                self._check_lane(account, symbol, mode, lot, ignore=lane.id)
                self._check_magic(account, magic, ignore=lane.id)
                magic = self._unique_magic(account, symbol, magic, ignore=lane.id)
                if 'name' in changes:
                    lane.name = self._lane_name(account, symbol, mode, changes['name'], ignore=lane.id)
                lane.account, lane.symbol, lane.mode = (account, clean_symbol(symbol), mode)
                lane.magic = int(magic) if magic is not None else None
                lane.lot = float(lot) if lot is not None else None
                lane.layering = changes.get('layering', lane.layering)
                lane.enabled = bool(changes.get('enabled', lane.enabled))
                if lane.settings is not None and lane.lot is not None:
                        lane.settings['lot'], lane.settings['lot_mode'] = (lane.lot, 'fixed')
                if 'distance' in changes:
                    lane.distance = sanitize_distance(changes['distance'])
        self.save()
        return lane
    def set_lane_distance(self, lane_id: str, distance: dict | None) -> LaneSpec:
        """Hanya ganti setelan jarak lane (None = ikut Pengaturan). Sengaja TIDAK menjalankan `_check_lane`:\n        batas lane/akun tidak relevan untuk perubahan ini."""
        with self._lock:
            lane = self.lane(lane_id)
            if lane is None:
                raise ArmadaError(tr('king.armada_err_no_lane'))
            else:
                lane.distance = sanitize_distance(distance)
        self.save()
        return lane
    def set_lane_config(self, lane_id: str, cfg: dict | None) -> LaneSpec:
        """Simpan SEMUA setelan pair (strategi, risiko, manajemen posisi, jarak) dari satu dict; None = ikut global.\n        Sengaja TIDAK menjalankan `_check_lane` (batas lane/akun tidak relevan)."""
        with self._lock:
            lane = self.lane(lane_id)
            if lane is None:
                raise ArmadaError(tr('king.armada_err_no_lane'))
            else:
                f = split_config(cfg)
                lane.mode, lane.lot, lane.layering = (f['mode'], f['lot'], f['layering'])
                lane.distance, lane.settings = (f['distance'], f['settings'])
        self.save()
        return lane
    def remove_lane(self, lane_id: str) -> None:
        with self._lock:
            self.lanes = [ln for ln in self.lanes if ln.id != lane_id]
            if self.focus == lane_id:
                self.focus = self.lanes[0].id if self.lanes else ''
        self.save()
    def set_focus(self, lane_id: str) -> None:
        with self._lock:
            if self.lane(lane_id) is None or self.focus == lane_id:
                return
            else:
                self.focus = lane_id
        self.save()
    def set_governor(self, **changes) -> GovernorConfig:
        with self._lock:
            g = self.governor
            g.max_positions = max(1, int(changes.get('max_positions', g.max_positions)))
            g.max_daily_loss = max(0.0, float(changes.get('max_daily_loss', g.max_daily_loss)))
            g.block_correlated = bool(changes.get('block_correlated', g.block_correlated))
            g.max_lanes_per_account = max(1, int(changes.get('max_lanes_per_account', g.max_lanes_per_account)))
        self.save()
        return self.governor