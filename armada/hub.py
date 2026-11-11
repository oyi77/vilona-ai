# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\armada\\hub.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nhub.py\n======\nSisi UI armada. Hub TIDAK pernah menyentuh MetaTrader5; ia menjalankan satu\nproses worker per akun (worker.py), bicara lewat protokol JSON-lines, dan\nmenyajikan ke UI objek-objek yang bentuknya sama dengan engine lama:\n\n    Armada      pusat: akun, lane, fokus, agregasi saldo/P&L, Risk Governor lintas akun\n    AccountLink satu proses worker (QProcess) + antrean permintaan/jawaban\n    LaneProxy   cermin satu lane: sinyal & metode seperti AutoTradeEngine\n                (running_changed, log_line, stats_changed, pipeline_step, ...)\n\nSemua berjalan di thread UI (sinyal QProcess), jadi tanpa kunci.\n"""
from __future__ import annotations
import itertools
import json
import os
import sys
import time
from armada import governor as gov
from armada import protocol as P
from armada.model import AccountSpec, ArmadaError, ArmadaStore, LaneSpec
from core.config import DATA_DIR, PROJECT_ROOT
from core.i18n import tr
from core.qt import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from trading import trading_rules
MAX_LOG_LINES = 300
REQ_TIMEOUT_MS = 60000
RESTART_DELAYS_MS = (1500, 4000, 10000)
SUMMARY_THROTTLE_MS = 250
GOVERNOR_THROTTLE_MS = 1000
WORKER_LOG_MAX = 524288
def worker_command(account_id: str) -> tuple[str, list[str]]:
    """(program, argumen) untuk menjalankan worker - sama untuk dev dan exe PyInstaller."""
    if getattr(sys, 'frozen', False):
        return (sys.executable, ['--worker', '--account', account_id])
    else:
        return (sys.executable, [str(PROJECT_ROOT / 'king_ai.py'), '--worker', '--account', account_id])
class LaneProxy(QObject):
    """Cermin satu lane di sisi UI - API & sinyal sama seperti AutoTradeEngine."""
    running_changed = Signal(bool)
    status_changed = Signal(str, str)
    log_line = Signal(str, str)
    stats_changed = Signal(dict)
    tick_changed = Signal(dict)
    tokens_changed = Signal(dict)
    management_changed = Signal(dict)
    signal_changed = Signal(dict)
    pipeline_step = Signal(str, str, str)
    thinking_changed = Signal(bool)
    order_opened = Signal(dict)
    trade_closed = Signal(float, str)
    governor_blocked = Signal(str)
    start_failed = Signal(str)
    spec_changed = Signal()
    def __init__(self, spec: LaneSpec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._running = False
        self._log = []
        self._stats = {}
        self._tick = {}
        self._signal = {}
        self._tokens = {'prompt': 0, 'completion': 0, 'total': 0}
        self._mgmt = {'be': False, 'trailing': False}
        self._status = ('idle', tr('king.status_idle'))
        self._thinking = False
        self._gov = ''
        self.pipeline = {}
        self.started_at = None
        self.starting = False
    @property
    def id(self) -> str:
        return self.spec.id
    @property
    def account(self) -> str:
        return self.spec.account
    def symbol(self) -> str:
        return self.spec.symbol
    def is_running(self) -> bool:
        return self._running
    def log_history(self) -> list[tuple[str, str]]:
        return list(self._log)
    def last_stats(self) -> dict:
        return dict(self._stats)
    def last_tick(self) -> dict:
        return dict(self._tick)
    def last_signal(self) -> dict:
        return dict(self._signal)
    def session_tokens(self) -> dict:
        return dict(self._tokens)
    def status(self) -> tuple[str, str]:
        return self._status
    def management(self) -> dict:
        return dict(self._mgmt)
    def is_thinking(self) -> bool:
        return self._thinking
    def governor_reason(self) -> str:
        return self._gov
    def clear_log(self) -> None:
        self._log.clear()
    def apply(self, kind: str, d: dict) -> None:
        if kind == P.EV_RUNNING:
            running = bool(d.get('running'))
            self._running = running
            self.starting = False
            self.started_at = time.time() if running else None
            if not running:
                self._thinking = False
                self.pipeline.clear()
            self.running_changed.emit(running)
        else:
            if kind == P.EV_STATUS:
                self._status = (str(d.get('kind') or ''), str(d.get('text') or ''))
                self.status_changed.emit(*self._status)
            else:
                if kind == P.EV_LOG:
                    line, level = (str(d.get('line') or ''), str(d.get('level') or 'info'))
                    if level.startswith('replace:'):
                        if self._log:
                            self._log[(-1)] = (line, level.split(':', 1)[1])
                    else:
                        self._log.append((line, level))
                        if len(self._log) > MAX_LOG_LINES:
                            del self._log[:len(self._log) - MAX_LOG_LINES]
                    self.log_line.emit(line, level)
                else:
                    if kind == P.EV_STATS:
                        self._stats = d
                        self.stats_changed.emit(dict(d))
                    else:
                        if kind == P.EV_TICK:
                            self._tick = d
                            self.tick_changed.emit(dict(d))
                        else:
                            if kind == P.EV_TOKENS:
                                self._tokens = d
                                self.tokens_changed.emit(dict(d))
                            else:
                                if kind == P.EV_MGMT:
                                    self._mgmt = d
                                    self.management_changed.emit(dict(d))
                                else:
                                    if kind == P.EV_SIGNAL:
                                        self._signal = d
                                        self.signal_changed.emit(dict(d))
                                    else:
                                        if kind == P.EV_PIPE:
                                            node, state, note = (str(d.get('node') or ''), str(d.get('state') or ''), str(d.get('note') or ''))
                                            if node == '*':
                                                self.pipeline.clear()
                                            else:
                                                if node:
                                                    self.pipeline[node] = (state, note)
                                            self.pipeline_step.emit(node, state, note)
                                        else:
                                            if kind == P.EV_THINKING:
                                                self._thinking = bool(d.get('on'))
                                                self.thinking_changed.emit(self._thinking)
                                            else:
                                                if kind == P.EV_ORDER:
                                                    self.order_opened.emit(dict(d))
                                                else:
                                                    if kind == P.EV_CLOSED:
                                                        self.trade_closed.emit(float(d.get('profit') or 0.0), str(d.get('strategy') or ''))
                                                    else:
                                                        if kind == P.EV_GOV:
                                                            self._gov = str(d.get('reason') or '')
                                                            self.governor_blocked.emit(self._gov)
    def mark_offline(self, text: str) -> None:
        """Worker mati / terputus: lane dianggap berhenti (sesi tetap di disk untuk dilanjutkan)."""
        was = self._running
        self._running = False
        self.starting = False
        self._thinking = False
        self.pipeline.clear()
        self._status = ('stopped', text)
        self.status_changed.emit(*self._status)
        if was:
            self.running_changed.emit(False)
class AccountLink(QObject):
    """Satu proses worker. Permintaan dikirim dengan nomor; jawaban dipasangkan lewat callback."""
    ready = Signal()
    lane_event = Signal(str, str, dict)
    stopped = Signal(bool)
    state_changed = Signal()
    def __init__(self, spec: AccountSpec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.proc = None
        self.is_ready = False
        self.pid = 0
        self.connected = False
        self.label = ''
        self.exe_path = ''
        self.symbols = []
        self.acc_mode = {}
        self.license = {}
        self.connecting = False
        self.balance = self.equity = self.margin_free = None
        self.currency = ''
        self.exposure = 0
        self.cpu = 0.0
        self.ram_mb = 0.0
        self._ids = itertools.count(1)
        self._pending = {}
        self._queue = []
        self._buf = b''
        self._stopping = False
        self._restarts = 0
        self._ps = None
    def alive(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.NotRunning
    def start(self) -> None:
        if self.alive():
            return
        else:
            self._stopping = False
            self.is_ready = False
            self._buf = b''
            self.proc = QProcess(self)
            env = QProcessEnvironment.systemEnvironment()
            env.insert('KINGAI_ACCOUNT_ID', self.spec.id)
            env.insert('PYTHONIOENCODING', 'utf-8')
            env.insert('PYTHONUNBUFFERED', '1')
            self.proc.setProcessEnvironment(env)
            self.proc.setWorkingDirectory(str(PROJECT_ROOT) if not getattr(sys, 'frozen', False) else os.getcwd())
            self.proc.readyReadStandardOutput.connect(self._on_stdout)
            self.proc.readyReadStandardError.connect(self._on_stderr)
            self.proc.finished.connect(self._on_finished)
            self.proc.errorOccurred.connect(self._on_error)
            try:
                self.proc.setCreateProcessArgumentsModifier(_no_window)
            except (AttributeError, TypeError):
                pass
            program, args = worker_command(self.spec.id)
            self.proc.start(program, args)
    def _on_error(self, error) -> None:
        if error == QProcess.FailedToStart:
            self._fail_all(tr('king.armada_worker_failed'))
            self.stopped.emit(True)
    def _on_stdout(self) -> None:
        self._buf += bytes(self.proc.readAllStandardOutput())
        while b'\n' in self._buf:
            line, self._buf = self._buf.split(b'\n', 1)
            msg = P.decode(line)
            if msg:
                self._dispatch(msg)
    def _on_stderr(self) -> None:
        data = bytes(self.proc.readAllStandardError())
        if not data:
            return
        else:
            try:
                path = DATA_DIR / f'worker_{self.spec.id}.log'
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and path.stat().st_size > WORKER_LOG_MAX:
                        path.write_bytes(path.read_bytes()[-WORKER_LOG_MAX // 2:])
                with open(path, 'ab') as f:
                    f.write(data)
            except OSError:
                return None
    def _dispatch(self, msg: dict) -> None:
        t = msg.get('t')
        if t == 'ready':
            self.is_ready = True
            self.pid = int(msg.get('pid') or 0)
            self._restarts = 0
            self._ps = None
            for chunk in self._queue:
                self.proc.write(chunk)
            self._queue.clear()
            self.state_changed.emit()
            self.ready.emit()
        else:
            if t == 'res':
                entry = self._pending.pop(int(msg.get('id') or 0), None)
                if entry:
                    cb, timer = entry
                    timer.stop()
                    timer.deleteLater()
                    if cb:
                        cb(bool(msg.get('ok')), msg.get('data'), str(msg.get('error') or ''))
            else:
                if t == 'ev':
                    lane, kind, data = (str(msg.get('lane') or ''), str(msg.get('k') or ''), msg.get('d') or {})
                    if not lane:
                        self._apply_account_event(kind, data)
                    self.lane_event.emit(lane, kind, data)
    def _apply_account_event(self, kind: str, d: dict) -> None:
        if kind == P.EV_ACCOUNT:
            self.connected = bool(d.get('connected'))
            self.label = str(d.get('label') or '')
            if isinstance(d.get('acc_mode'), dict):
                self.acc_mode = dict(d['acc_mode'])
            if not self.connected:
                self.exposure = 0
        else:
            if kind == P.EV_LICENSE:
                self.license = {k: d.get(k) for k in ['login', 'entered', 'status', 'grace', 'message']}
            else:
                if kind == P.EV_ACCT_STATS:
                    self.balance, self.equity, self.margin_free = (d.get('balance'), d.get('equity'), d.get('margin_free'))
                    self.currency = str(d.get('currency') or '')
                    self.exposure = int(d.get('exposure') or 0)
        self.state_changed.emit()
    def _on_finished(self, _code, _status) -> None:
        unexpected = not self._stopping
        self.is_ready = False
        self.connected = False
        self.connecting = False
        self.exposure = 0
        self.pid = 0
        self.license = {}
        self._fail_all(tr('king.armada_worker_stopped'))
        self.state_changed.emit()
        self.stopped.emit(unexpected)
    def _fail_all(self, text: str) -> None:
        pending, self._pending = (self._pending, {})
        for cb, timer in pending.values():
            timer.stop()
            timer.deleteLater()
            if cb:
                cb(False, None, text)
        self._queue.clear()
    def restart_delay(self) -> int | None:
        """Jeda sebelum mencoba hidupkan ulang worker yang mati sendiri (None = menyerah)."""
        if self._restarts >= len(RESTART_DELAYS_MS):
            return
        else:
            delay = RESTART_DELAYS_MS[self._restarts]
            self._restarts += 1
            return delay
    def req(self, op: str, args: dict | None=None, cb=None, timeout_ms: int=REQ_TIMEOUT_MS) -> None:
        if not self.alive():
            self.start()
        rid = next(self._ids)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._timeout(rid))
        timer.start(timeout_ms)
        self._pending[rid] = (cb, timer)
        data = P.request(rid, op, args)
        if self.is_ready:
            self.proc.write(data)
        else:
            self._queue.append(data)
    def _timeout(self, rid: int) -> None:
        entry = self._pending.pop(rid, None)
        if entry:
            cb, timer = entry
            timer.deleteLater()
            if cb:
                cb(False, None, tr('king.armada_timeout'))
    def stop(self, wait_ms: int=3000) -> None:
        """Hentikan worker dengan sopan (tidak menutup posisi)."""
        self._stopping = True
        if not self.alive():
            return
        else:
            if self.is_ready:
                self.proc.write(P.request(next(self._ids), P.OP_SHUTDOWN))
            self.proc.closeWriteChannel()
            if not self.proc.waitForFinished(wait_ms):
                self.proc.kill()
                self.proc.waitForFinished(1000)
    def sample_resources(self) -> None:
        if not self.pid:
            self.cpu = self.ram_mb = 0.0
            return
        else:
            try:
                import psutil
                if self._ps is None or self._ps.pid != self.pid:
                    self._ps = psutil.Process(self.pid)
                    self._ps.cpu_percent(None)
                self.cpu = self._ps.cpu_percent(None)
                self.ram_mb = self._ps.memory_info().rss / 1048576
            except Exception:
                self.cpu = self.ram_mb = 0.0
def _no_window(args) -> None:
    args.flags |= 134217728
class Armada(QObject):
    """Pusat armada untuk UI."""
    topology_changed = Signal()
    focus_changed = Signal(str)
    account_changed = Signal(str)
    summary_changed = Signal()
    lane_running_changed = Signal(str, bool)
    any_running_changed = Signal(bool)
    notice = Signal(str, bool)
    trade_closed = Signal(float, str)
    def __init__(self, store: ArmadaStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.links = {}
        self._pending_starts = set()
        self.proxies = {}
        self._was_running = False
        self._last_ext = {}
        self._synced = set()
        self._summary_timer = QTimer(self)
        self._summary_timer.setSingleShot(True)
        self._summary_timer.setInterval(SUMMARY_THROTTLE_MS)
        self._summary_timer.timeout.connect(self._flush_summary)
        self._gov_timer = QTimer(self)
        self._gov_timer.setSingleShot(True)
        self._gov_timer.setInterval(GOVERNOR_THROTTLE_MS)
        self._gov_timer.timeout.connect(self._push_governor)
        self._res_timer = QTimer(self)
        self._res_timer.setInterval(2000)
        self._res_timer.timeout.connect(self._sample_resources)
        self._res_timer.start()
        self.rebuild()
    def rebuild(self) -> None:
        """Samakan LaneProxy / AccountLink dengan isi store."""
        lanes = {ln.id: ln for ln in self.store.lanes}
        for lane_id in list(self.proxies):
            if lane_id not in lanes:
                proxy = self.proxies.pop(lane_id)
                proxy.deleteLater()
        for spec in lanes.values():
            proxy = self.proxies.get(spec.id)
            if proxy is None:
                proxy = LaneProxy(spec, self)
                proxy.running_changed.connect(lambda r, lid=spec.id: self._on_lane_running(lid, r))
                proxy.stats_changed.connect(self._on_lane_stats)
                proxy.trade_closed.connect(self.trade_closed)
                self.proxies[spec.id] = proxy
            else:
                proxy.spec = spec
                proxy.spec_changed.emit()
        accounts = {a.id: a for a in self.store.accounts}
        for acc_id in list(self.links):
            if acc_id not in accounts:
                link = self.links.pop(acc_id)
                link.stop()
                link.deleteLater()
        for spec in accounts.values():
            link = self.links.get(spec.id)
            if link is None:
                link = AccountLink(spec, self)
                link.lane_event.connect(lambda lane, kind, data, aid=spec.id: self._on_event(aid, lane, kind, data))
                link.state_changed.connect(lambda aid=spec.id: self._on_account_state(aid))
                link.stopped.connect(lambda unexpected, aid=spec.id: self._on_stopped(aid, unexpected))
                self.links[spec.id] = link
            else:
                link.spec = spec
        trading_rules.set_known_magics((ln.effective_magic() for ln in self.store.lanes))
        self.topology_changed.emit()
    def lane_list(self) -> list[LaneProxy]:
        return [self.proxies[ln.id] for ln in self.store.lanes if ln.id in self.proxies]
    def lanes_of(self, account_id: str) -> list[LaneProxy]:
        return [p for p in self.lane_list() if p.account == account_id]
    def proxy(self, lane_id: str) -> LaneProxy | None:
        return self.proxies.get(lane_id)
    def focused(self) -> LaneProxy | None:
        return self.proxies.get(self.store.focus) or (self.lane_list()[0] if self.proxies else None)
    def set_focus(self, lane_id: str) -> None:
        if lane_id in self.proxies and self.store.focus != lane_id:
                self.store.set_focus(lane_id)
                self.focus_changed.emit(lane_id)
    def cycle_focus(self) -> None:
        lanes = self.lane_list()
        if len(lanes) > 1:
            cur = self.focused()
            self.set_focus(lanes[(lanes.index(cur) + 1) % len(lanes)].id if cur in lanes else lanes[0].id)
    def account(self, account_id: str) -> AccountLink | None:
        return self.links.get(account_id)
    def add_account(self, name: str, path: str='') -> AccountSpec:
        spec = self.store.add_account(name, path)
        self.rebuild()
        return spec
    def update_account(self, account_id: str, **changes) -> AccountSpec:
        spec = self.store.update_account(account_id, **changes)
        self.rebuild()
        self._sync_account(account_id)
        return spec
    def remove_account(self, account_id: str) -> None:
        self.store.remove_account(account_id)
        self.rebuild()
    def add_lane(self, account_id: str, symbol: str, **kw) -> LaneSpec:
        spec = self.store.add_lane(account_id, symbol, **kw)
        self.rebuild()
        self._sync_account(account_id)
        return spec
    def update_lane(self, lane_id: str, **changes) -> LaneSpec:
        proxy = self.proxies.get(lane_id)
        if proxy is not None and proxy.is_running():
            raise ArmadaError(tr('king.armada_err_running'))
        else:
            old = self.store.lane(lane_id)
            old_account = old.account if old else ''
            spec = self.store.update_lane(lane_id, **changes)
            self.rebuild()
            for acc in {old_account, spec.account}:
                if acc:
                    self._sync_account(acc)
            return spec
    def set_lane_distance(self, lane_id: str, distance: dict | None) -> LaneSpec:
        proxy = self.proxies.get(lane_id)
        if proxy is not None and proxy.is_running():
            raise ArmadaError(tr('king.armada_err_running'))
        else:
            spec = self.store.set_lane_distance(lane_id, distance)
            self.rebuild()
            self._sync_account(spec.account)
            return spec
    def set_lane_config(self, lane_id: str, cfg: dict | None) -> LaneSpec:
        proxy = self.proxies.get(lane_id)
        if proxy is not None and proxy.is_running():
            raise ArmadaError(tr('king.armada_err_running'))
        else:
            spec = self.store.set_lane_config(lane_id, cfg)
            self.rebuild()
            self._sync_account(spec.account)
            return spec
    def remove_lane(self, lane_id: str) -> None:
        proxy = self.proxies.get(lane_id)
        if proxy is not None and proxy.is_running():
            raise ArmadaError(tr('king.armada_err_running'))
        else:
            lane = self.store.lane(lane_id)
            self.store.remove_lane(lane_id)
            self.rebuild()
            if lane:
                self._sync_account(lane.account)
            self.focus_changed.emit(self.store.focus)
    def set_governor(self, **changes) -> None:
        self.store.set_governor(**changes)
        self._last_ext.clear()
        self._push_governor()
    def _payload(self, account_id: str) -> dict:
        # ***<module>.Armada._payload: Failure: Different bytecode
        acc = self.store.account(account_id)
        str = [vars(ln) for ln in self.store.lanes_of(account_id)]
        account_mode = acc.account_mode if acc else 'auto'
        acc = acc.license_id if acc else ''
        return {'lanes': vars(self.store.governor), 'account_mode': self._external(account_id).to_dict(), 'license_id': self._external(account_id).to_dict(), 'governor': self._external(account_id).to_dict()}
    def _sync_account(self, account_id: str) -> None:
        link = self.links.get(account_id)
        if link is not None and link.alive():
                link.req(P.OP_SYNC, self._payload(account_id))
    def connect_account(self, account_id: str, cb=None) -> None:
        """Hidupkan worker akun lalu sambungkan ke terminalnya; cb(ok, pesan, daftar symbol)."""
        # ***<module>.Armada.connect_account: Failure: Different bytecode
        link = self.links.get(account_id)
        if link is None:
            if cb:
                cb(False, tr('king.armada_err_no_account'), [])
            return None
        else:
            if link.connecting:
                return
            else:
                link.connecting = True
                link.state_changed.emit()
                link.req(P.OP_RELOAD)
                link.req(P.OP_SYNC, self._payload(account_id))
                def done(ok, data, error):
                    # ***<module>.Armada.connect_account.done: Failure: Different bytecode
                    data.connecting = False
                    if ok and cb:
                        data.symbols = list(cb.get('symbols') or [])
                        data.exe_path = cb.get('exe') or ''
                        data.connected = bool(cb.get('ok'))
                        data.label = cb.get('label') or ''
                        if isinstance(cb.get('acc_mode'), dict):
                            data.acc_mode = dict(cb['acc_mode'])
                        if isinstance(cb.get('license'), dict):
                            str = {k: data['license'].get(k) for k in cb.account_id}
                            data.license = ('login', 'entered', 'status', 'grace', 'message')
                        data.state_changed.emit()
                        if link:
                            link(bool(cb.get('ok')), str(cb.get('msg') or ''), data.symbols)
                    else:
                        data.state_changed.emit()
                        if link:
                            link(False, error or tr('king.armada_worker_failed'), [])
                link.req(P.OP_CONNECT, link.spec.path, link.spec.account_mode, account_id=True)
                link.spec.license_id({'path': 'path', 'account_mode': 'account_mode', 'license_id': link.spec.license_id}, done, timeout_ms=90000)
    def connect_all(self) -> None:
        for acc in self.store.accounts:
            if acc.auto_connect:
                self.connect_account(acc.id)
    def reload_workers(self) -> None:
        """Pengaturan Autotrade / model / bahasa disimpan di Hub -> worker membaca ulang dari disk."""
        for link in self.links.values():
            if link.alive():
                link.req(P.OP_RELOAD)
    def request(self, account_id: str, op: str, args: dict | None=None, cb=None, timeout_ms: int=REQ_TIMEOUT_MS):
        link = self.links.get(account_id)
        if link is None or not link.alive() or (not link.connected):
            if cb:
                cb(False, None, tr('king.armada_account_offline'))
            return None
        else:
            link.req(op, args, cb, timeout_ms)
    def online_accounts(self) -> list[str]:
        return [a.id for a in self.store.accounts if self.links.get(a.id) and self.links[a.id].connected]
    def license_block(self, account_id: str) -> str | None:
        """Pesan penolakan Start bila akun yang SUDAH tersambung jelas tidak berlisensi.\n        Akun yang belum tersambung / belum selesai dicek dibiarkan lewat - worker tetap\n        menegakkan lisensi saat lane benar-benar di-Start (AutoTradeEngine.preflight)."""
        from core import account_license
        acc = self.store.account(account_id)
        if acc is not None and (not acc.license_id):
            return tr('king.lic_lane_missing')
        else:
            link = self.links.get(account_id)
            if link is None or not link.connected:
                return None
            else:
                lic = link.license or {}
                if lic.get('status') in [account_license.UNLICENSED, account_license.MISSING, account_license.MISMATCH]:
                    return account_license.reason_for(lic)
                else:
                    return None
    def check_license(self, account_id: str, cb=None) -> None:
        """Minta worker mengecek ulang lisensi login MT5 akun ini; cb(ok, dict lisensi | None, error)."""
        self.request(account_id, P.OP_LICENSE, {}, cb, timeout_ms=30000)
    def start_lane(self, lane_id: str) -> None:
        proxy = self.proxies.get(lane_id)
        if proxy is None or proxy.is_running() or proxy.starting:
            return None
        else:
            spec = proxy.spec
            link = self.links.get(spec.account)
            if link is None:
                return
            else:
                if not spec.enabled:
                    proxy.start_failed.emit(tr('king.armada_lane_disabled', symbol=spec.symbol))
                    return
                else:
                    blocked = self.license_block(spec.account)
                    if blocked:
                        proxy.start_failed.emit(blocked)
                        return
                    else:
                        proxy.starting = True
                        proxy.status_changed.emit('busy', tr('king.cmd_starting'))
                        def launch():
                            link.req(P.OP_RELOAD)
                            link.req(P.OP_SYNC, self._payload(spec.account))
                            def done(ok, data, error):
                                proxy.starting = False
                                problem = error if not ok else (data or {}).get('error')
                                if problem:
                                    proxy.start_failed.emit(str(problem))
                                    proxy.status_changed.emit(*proxy.status())
                            link.req(P.OP_LANE_START, {'lane': lane_id}, done)
                        if link.connected:
                            launch()
                        else:
                            def connected(ok, msg, _symbols):
                                if ok:
                                    launch()
                                else:
                                    proxy.starting = False
                                    proxy.start_failed.emit(msg)
                                    proxy.status_changed.emit(*proxy.status())
                            self.connect_account(spec.account, connected)
    def stop_lane(self, lane_id: str, close_positions: bool=True) -> None:
        # ***<module>.Armada.stop_lane: Failure: Different control flow
        self._pending_starts.discard(lane_id)
        proxy = self.proxies.get(lane_id)
        link = self.links.get(proxy.account) if proxy else None
        if proxy is None or link is None or (not link.alive()):
            if proxy is not None and proxy.starting:
                    proxy.starting = False
                    proxy.status_changed.emit(*proxy.status())
            return None
        else:
            link.req(P.OP_LANE_STOP, {'lane': lane_id, 'close': close_positions})
            if not proxy.starting or not proxy.is_running():
                    proxy.starting = False
                    proxy.status_changed.emit(*proxy.status())
    def start_all(self) -> int:
        """Mulai semua lane aktif yang belum berjalan; kembalikan jumlahnya."""
        targets = [p for p in self.lane_list() if p.spec.enabled and (not p.is_running()) and (not p.starting)]
        blocked = [p for p in targets if self.license_block(p.account)]
        if blocked:
            targets = [p for p in targets if p not in blocked]
            self.notice.emit(tr('king.lic_start_all_skipped', n=len(blocked)), True)
        for i, proxy in enumerate(targets):
            self._pending_starts.add(proxy.id)
            QTimer.singleShot(i * 400, lambda lid=proxy.id: self._start_pending(lid))
        return len(targets)
    def _start_pending(self, lane_id: str) -> None:
        """Start terjadwal milik Start Semua - dilewati bila sudah dibatalkan (Stop) sebelum gilirannya."""
        if lane_id in self._pending_starts:
            self._pending_starts.discard(lane_id)
            self.start_lane(lane_id)
    def stop_all(self, close_positions: bool=True) -> None:
        self._pending_starts.clear()
        for proxy in self.lane_list():
            if proxy.is_running() or proxy.starting:
                self.stop_lane(proxy.id, close_positions)
    def running_count(self) -> int:
        return sum((1 for p in self.proxies.values() if p.is_running()))
    def any_running(self) -> bool:
        return self.running_count() > 0
    def any_active(self) -> bool:
        """Ada lane berjalan ATAU sedang memulai (bisa dihentikan)."""
        return bool(self._pending_starts) or any((p.is_running() or p.starting for p in self.proxies.values()))
    def _on_event(self, account_id: str, lane_id: str, kind: str, data: dict) -> None:
        proxy = self.proxies.get(lane_id) if lane_id else None
        if proxy is not None:
            proxy.apply(kind, data)
        else:
            if not lane_id and kind == P.EV_LICENSE and data.get('notice'):
                        link = self.links.get(account_id)
                        name = link.spec.name if link else account_id
                        key = 'king.lic_revoked' if data['notice'] == 'revoked' else 'king.lic_login_changed'
                        self.notice.emit(tr(key, name=name, login=data.get('login') or '-'), True)
    def _on_lane_running(self, lane_id: str, running: bool) -> None:
        self.lane_running_changed.emit(lane_id, running)
        now = self.any_running()
        if now != self._was_running:
            self._was_running = now
            self.any_running_changed.emit(now)
        self._schedule_summary()
    def _on_lane_stats(self, _stats: dict) -> None:
        self._schedule_summary()
    def _on_account_state(self, account_id: str) -> None:
        self.account_changed.emit(account_id)
        self._schedule_summary()
    def _on_stopped(self, account_id: str, unexpected: bool) -> None:
        link = self.links.get(account_id)
        if link is None:
            return
        else:
            for proxy in self.lanes_of(account_id):
                proxy.mark_offline(tr('king.armada_worker_stopped'))
            self.account_changed.emit(account_id)
            if not unexpected:
                return
            else:
                name = link.spec.name
                delay = link.restart_delay()
                if delay is None:
                    self.notice.emit(tr('king.armada_worker_gave_up', name=name), True)
                    return
                else:
                    self.notice.emit(tr('king.armada_worker_crashed', name=name), True)
                    QTimer.singleShot(delay, lambda: self._restart(account_id))
    def _restart(self, account_id: str) -> None:
        link = self.links.get(account_id)
        if link is not None and (not link.alive()):
                self.connect_account(account_id)
    def summary(self, scope: str='all') -> dict:
        """Ringkasan ala stats engine untuk satu akun / semua akun."""
        # ***<module>.Armada.summary: Failure: Compilation Error
        links = [l for a, l in self.links.items() if scope == 'all' or a == scope]
        lanes = [p for p in self.lane_list() if scope == 'all' or p.account == scope]
        online = [l for l in links if l.balance is not None]
        stats = [p.last_stats() for p in lanes if p.last_stats()]
        currencies = {l.currency for l in online if l.currency}
        currency = next(iter(currencies)) if len(currencies) == 1 else ''
        balance_values = [l.balance for l in online if l.balance is not None]
        equity_values = [l.equity for l in online if l.equity is not None]
        margin_values = [l.margin_free for l in online if l.margin_free is not None]
        return {
            'balance': sum(balance_values) if balance_values else None,
            'equity': sum(equity_values) if equity_values else None,
            'margin_free': sum(margin_values) if margin_values else None,
            'currency': currency,
            'mixed_currency': len(currencies) > 1,
            'floating': sum(s.get('floating') or 0.0 for s in stats),
            'positions': sum(s.get('positions') or 0 for s in stats),
            'pendings': sum(s.get('pendings') or 0 for s in stats),
            'daily': sum(s.get('daily') or 0.0 for s in stats),
            'wins': sum(s.get('wins') or 0 for s in stats),
            'closed': sum(s.get('closed') or 0 for s in stats),
            'accounts': len(links),
            'online': len(online),
            'lanes': len(lanes),
            'running': sum(1 for p in lanes if p.is_running()),
        }
    def session_tokens(self, scope: str='all') -> dict:
        total = {'prompt': 0, 'completion': 0, 'total': 0}
        for p in self.lane_list():
            if scope == 'all' or p.account == scope:
                for k in total:
                    total[k] += int(p.session_tokens().get(k, 0))
        return total
    def _schedule_summary(self) -> None:
        if not self._summary_timer.isActive():
            self._summary_timer.start()
        if not self._gov_timer.isActive():
            self._gov_timer.start()
    def _flush_summary(self) -> None:
        self.summary_changed.emit()
    def _external(self, account_id: str) -> gov.External:
        exposure = {a: l.exposure for a, l in self.links.items()}
        daily = {}
        for p in self.lane_list():
            daily[p.account] = daily.get(p.account, 0.0) + float(p.last_stats().get('daily') or 0.0)
        return gov.external_for(self.store.governor, account_id, exposure, daily)
    def _push_governor(self) -> None:
        """Kirim keadaan akun lain ke tiap worker bila berubah (batas gabungan, halt rugi harian)."""
        for acc in self.store.accounts:
            link = self.links.get(acc.id)
            if link is None or not link.alive() or (not link.is_ready):
                continue
            else:
                ext = self._external(acc.id).to_dict()
                if self._last_ext.get(acc.id) != ext:
                    self._last_ext[acc.id] = ext
                    link.req(P.OP_GOVERNOR, {'governor': vars(self.store.governor), 'external': ext})
    def _sample_resources(self) -> None:
        changed = False
        for link in self.links.values():
            if link.alive():
                link.sample_resources()
                changed = True
        if changed:
            for acc_id in self.links:
                self.account_changed.emit(acc_id)
    def fetch_history(self, account_ids: list[str], start_iso: str, end_iso: str, cb) -> None:
        """cb({account_id: data | {\"error\": str}}) setelah SEMUA akun menjawab."""
        results = {}
        targets = [a for a in account_ids if self.links.get(a) and self.links[a].connected]
        for a in account_ids:
            if a not in targets:
                results[a] = {'error': tr('king.armada_account_offline')}
        if not targets:
            cb(results)
            return
        else:
            remaining = {'n': len(targets)}
            def make(acc):
                def done(ok, data, error):
                    results[acc] = data if ok and isinstance(data, dict) else {'error': error or '?'}
                    remaining['n'] -= 1
                    if remaining['n'] == 0:
                        cb(results)
                return done
            for acc in targets:
                self.links[acc].req(P.OP_HISTORY, {'start': start_iso, 'end': end_iso}, make(acc))
    def probe_history(self, account_ids: list[str], start_iso: str, cb) -> None:
        """cb(tanda tangan gabungan | None bila tidak ada akun online)."""
        targets = [a for a in account_ids if self.links.get(a) and self.links[a].connected]
        if not targets:
            cb(None)
            return
        else:
            sigs = {}
            remaining = {'n': len(targets)}
            def make(acc):
                def done(ok, data, _error):
                    sigs[acc] = data if ok else None
                    remaining['n'] -= 1
                    if remaining['n'] == 0:
                        cb(json.dumps(sigs, sort_keys=True))
                return done
            for acc in targets:
                self.links[acc].req(P.OP_PROBE, {'start': start_iso}, make(acc))
    def fetch_open(self, account_ids: list[str], cb) -> None:
        results = {}
        targets = [a for a in account_ids if self.links.get(a) and self.links[a].connected]
        if not targets:
            cb(results)
            return
        else:
            remaining = {'n': len(targets)}
            def make(acc):
                def done(ok, data, _error):
                    results[acc] = data if ok and isinstance(data, list) else []
                    remaining['n'] -= 1
                    if remaining['n'] == 0:
                        cb(results)
                return done
            for acc in targets:
                self.links[acc].req(P.OP_OPEN, {}, make(acc))
    def shutdown(self) -> None:
        """Aplikasi ditutup: worker berhenti sopan (posisi & snapshot sesi dibiarkan)."""
        for link in self.links.values():
            link.stop()