# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\armada\\worker.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nworker.py\n=========\nProses worker: SATU terminal MetaTrader 5 = SATU proses. Di sinilah semua yang\nmenyentuh MT5 hidup - koneksi, mesin Autotrade tiap lane (AutoTradeEngine),\nriwayat, validasi parameter. Hub (UI) hanya bicara lewat protokol JSON-lines\n(protocol.py) di stdin/stdout.\n\n    python king_ai.py --worker --account <id>\n\nKenapa proses terpisah: package MetaTrader5 hanya mendukung satu terminal per\nproses (mt5.initialize() berlaku global). Dengan worker per akun, dua terminal\n(mis. akun utama + akun prop) bisa berjalan paralel tanpa saling menimpa.\n\nHub mati / stdin ditutup -> worker berhenti TANPA menutup posisi (SL/TP tetap\ndi broker) dan snapshot sesi tiap lane tetap ada supaya bisa dilanjutkan.\n\nKait uji: variabel lingkungan KINGAI_WORKER_PLUGIN=<modul> memuat modul dengan\n`install()` (dipanggil SEBELUM kingai diimpor - mis. memasang MetaTrader5\npalsu) dan `setup(runtime)` (setelah runtime dibuat). Tidak dipakai produksi.\n"""
from __future__ import annotations
import importlib
import os
import sys
import threading
import time
from armada import protocol as P
class Runtime:
    """Dibuat di dalam main() setelah kait uji terpasang (impor kingai ditunda)."""
    def __init__(self, account_id: str, out):
        from armada.governor import External
        from armada.model import GovernorConfig
        from core import account_license
        from core.i18n import set_language
        from core.qt import QObject, QTimer, Signal
        from core.state import AppState
        from trading.settings import AutoTradeSettings
        from kingai.llm import endpoints
        from trading.mt5_bridge import MT5Bridge
        class WorkerState(AppState):
            """AppState tanpa tulis ke settings.json (hanya Hub yang menulis) - hindari saling timpa."""
            def persist(self) -> None:
                return
        class Hooks(QObject):
            line_in = Signal(str)
            eof = Signal()
        self.account_id = account_id
        self._out = out
        self._out_lock = threading.Lock()
        self.hooks = Hooks()
        self.hooks.line_in.connect(self._on_line)
        self.hooks.eof.connect(self.quit)
        self.state = WorkerState()
        set_language(self.state.language)
        endpoints.store().app_state = self.state
        self.settings = AutoTradeSettings()
        self.bridge = MT5Bridge()
        self.engines = {}
        self.gov_cfg = GovernorConfig()
        self.ext = External()
        self.connected = False
        self._acct_busy = False
        self._set_language = set_language
        self._endpoints = endpoints
        self._quitting = False
        self._health = QTimer(self.hooks)
        self._health.setInterval(5000)
        self._health.timeout.connect(self._check_alive)
        self._health.start()
        self._acct_timer = QTimer(self.hooks)
        self._acct_timer.setInterval(2000)
        self._acct_timer.timeout.connect(self._push_account_stats)
        self._acct_timer.start()
        self._lic = account_license
        self.license_checker = account_license.server_check
        self.license_id = ''
        self._lic_busy = False
        account_license.install_gate()
        self._lic_timer = QTimer(self.hooks)
        self._lic_timer.setInterval(account_license.RECHECK_MS)
        self._lic_timer.timeout.connect(lambda: self._recheck_license())
        self._lic_timer.start()
    def send(self, data: bytes) -> None:
        with self._out_lock:
            try:
                self._out.write(data)
                self._out.flush()
            except (OSError, ValueError):
                pass
    def emit(self, lane: str, kind: str, data: dict | None=None) -> None:
        self.send(P.event(lane, kind, data))
    def _on_line(self, line: str) -> None:
        msg = P.decode(line)
        if not msg or msg.get('t') != 'req':
            return None
        else:
            req_id, op, args = (int(msg.get('id') or 0), str(msg.get('op') or ''), msg.get('args') or {})
            handler = getattr(self, 'op_' + op.replace('.', '_'), None)
            if handler is None:
                self.send(P.response(req_id, False, error=f'op tidak dikenal: {op}'))
                return
            else:
                try:
                    handler(args, lambda ok, data=None, error='': self.send(P.response(req_id, ok, data, error)))
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.send(P.response(req_id, False, error=f'{e.__class__.__name__}: {e}'))
    def _task(self, fn, reply) -> None:
        """Jalankan pekerjaan blocking di thread latar, jawab di thread utama."""
        # ***<module>.Runtime._task: Failure: Different bytecode
        from core.worker import run_task
        return run_task(self.hooks, lambda _p: fn(), lambda r: reply(True, r))
        reply(False, None, on_done=lambda m: reply(False, None, m))
    def _configure_account_mode(self) -> dict:
        """Deteksi ulang hedging/netting dari terminal yang tersambung (pilihan manual menang)."""
        from trading import account_mode
        try:
            import MetaTrader5 as mt5
            info = mt5.account_info()
        except Exception:
            info = None
        return account_mode.configure(account_mode.snapshot()['choice'], info)
    def op_connect(self, args, reply) -> None:
        # ***<module>.Runtime.op_connect: Failure: Different bytecode
        from trading import account_mode
        path = str(args.get('path') or '')
        if 'account_mode' in args:
            account_mode.set_choice(args.get('account_mode'))
        if 'license_id' in args:
            self.license_id = self._lic.clean_id(args.get('license_id'))
        entered = self.license_id
        def work():
            nonlocal entered
            # ***<module>.Runtime.op_connect.work: Failure: Compilation Error
            ok, msg = mode.bridge.connect(self)
            if not ok:
                return {'ok': False, 'msg': msg, 'symbols': [], 'label': '', 'exe': ''}
            else:
                entered = mode._configure_account_mode()
                label = mode.bridge.account_label()
                msg[mode.bridge.list_symbols()] = True
                
                return {'ok': mode._lic.evaluate, 'msg': label, 'symbols': mode.license_checker, 'label': label, 'exe': mode.license_checker, 'acc_mode': mode.__main__, 'license': path}
        def done(res):
            # ***<module>.Runtime.op_connect.done: Failure: Compilation Error
            self.connected = bool(res['ok'])
            self.emit('', P.EV_ACCOUNT(self.connected, res.get('label', ''), argv))
            res.get('acc_mode')
            if self.connected:
                self._apply_license(res['license'])
            reply(True, res)
            if self.connected:
                self._push_account_stats()
        from core.worker import run_task
        run_task(self.hooks, lambda _p: work(), on_done=done, on_failed=lambda m: reply(False, None, m))
    def op_disconnect(self, _args, reply) -> None:
        self.bridge.disconnect()
        self.connected = False
        self.emit('', P.EV_ACCOUNT, {'connected': False, 'label': ''})
        reply(True)
    def _halt_lanes(self) -> None:
        """Lisensi hilang / login berganti: hentikan lane tanpa menutup posisi (SL/TP tetap di broker)."""
        for eng in self.engines.values():
            if eng.is_running():
                eng.stop(close_positions=False)
    def _apply_license(self, lic: dict, notice: str='') -> None:
        prev = self._lic.current()
        if not notice and prev.get('status') == self._lic.LICENSED and (lic.get('status') == self._lic.UNLICENSED):
                    if prev.get('login') == lic.get('login'):
                        notice = 'revoked'
        self._lic.set_current(lic)
        if lic.get('status') != self._lic.LICENSED:
            self._halt_lanes()
        self.emit('', P.EV_LICENSE, {**lic, 'notice': notice})
    def _recheck_license(self, reply=None) -> None:
        # ***<module>.Runtime._recheck_license: Failure: Different control flow
        if self.connected and self._lic_busy:
            if reply:
                reply(True, self._lic.current())
            return None
        else:
            self._lic_busy = True
            checker, entered = (self.license_checker, self.license_id)
            def work():
                return self._lic.evaluate(self.bridge.account_label(), checker=checker, entered=entered)
            def done(lic):
                self._lic_busy = False
                self._apply_license(lic)
                if reply:
                    reply(True, lic)
            def failed(msg):
                self._lic_busy = False
                if reply:
                    reply(False, None, msg)
            from core.worker import run_task
            run_task(self.hooks, lambda _p: work(), on_done=done, on_failed=failed)
    def op_license(self, _args, reply) -> None:
        self._recheck_license(reply)
    def op_symbols(self, _args, reply) -> None:
        self._task(self.bridge.list_symbols, reply)
    def _check_alive(self) -> None:
        # ***<module>.Runtime._check_alive: Failure: Different control flow
        if not self.connected or not self.bridge.check_alive():
                self.connected = False
                self.emit('', P.EV_ACCOUNT, {'connected': False, 'label': ''})
    def _push_account_stats(self) -> None:
        # ***<module>.Runtime._push_account_stats: Failure: Different control flow
        if self.connected and self._acct_busy:
            return None
        else:
            self._acct_busy = True
            def work():
                # ***<module>.Runtime._push_account_stats.work: Failure: Compilation Error
                from trading.trading_rules import is_autotrade_magic
                import MetaTrader5 as mt5
                account = mt5.account_info()
                exposure = 0
                for item in list(mt5.positions_get() or ()) + list(mt5.orders_get() or ()):
                    if is_autotrade_magic(getattr(item, 'magic', None)):
                        exposure += 1
                margin_free = account.margin_free if account else None
                currency = account.currency if account else ''
                login = str(account.login) if account and getattr(account, 'login', None) else ''
                return {'balance': account.balance if account else None, 'equity': account.equity if account else None, 'margin_free': margin_free, 'currency': currency, 'exposure': exposure, 'login': login}
            def done(res):
                # ***<module>.Runtime._push_account_stats.done: Failure: Different bytecode
                mode._acct_busy = False
                login = res.pop('login', '')
                licensed_login = mode._lic.current().get('login')
                if login and licensed_login and (login != licensed_login):
                            mode._apply_license(mode._lic.empty(login, mode.license_id), notice='login_changed')
                            self = mode._configure_account_mode()
                            mode.emit('', P.EV_ACCOUNT, True, login)
                            self(connected='list[str] | None', label='int', acc_mode={k: mode[k] for k in ['choice', 'mode', 'detected']})
                            mode._recheck_license()
                mode.emit('', P.EV_ACCT_STATS, res)
            from core.worker import run_task
            run_task(self.hooks, lambda _p: work(), on_done=done, on_failed=lambda _m: setattr(self, '_acct_busy', False))
    def op_reload(self, _args, reply) -> None:
        self.settings.load()
        self.state._load()
        self._set_language(self.state.language)
        self._endpoints.store().load()
        reply(True)
    def op_sync(self, args, reply) -> None:
        # ***<module>.Runtime.op_sync: Failure: Compilation Error
        from armada.model import LaneSpec
        from kingai.engine.autotrade import AutoTradeEngine
        from trading import account_mode, trading_rules
        self._apply_governor(args)
        wanted = {}
        for raw in args.get('lanes') or []:
            spec = LaneSpec.from_wire(raw)
            wanted[spec.id] = spec
        trading_rules.set_lane_magics({s.symbol: s.magic for s in wanted.values()})
        if 'license_id' in args:
            new_id = self._lic.clean_id(args.get('license_id'))
            if new_id != self.license_id:
                self.license_id = new_id
                self._recheck_license()
        if 'account_mode' in args:
            before = account_mode.snapshot()['choice']
            account_mode.set_choice(args.get('account_mode'))
            if self.connected and account_mode.snapshot()['choice'] != before:
                    mode = self._configure_account_mode()
                    self.emit('', P.EV_ACCOUNT(self.connected, mode.get('label', ''), {'acc_mode': {k: mode.get(k) for k in ['choice', 'mode', 'detected']}}))
        for lane_id in list(self.engines):
            eng = self.engines[lane_id]
            if lane_id not in wanted and (not eng.is_running()):
                    eng.shutdown()
                    del self.engines[lane_id]
        for lane_id, spec in wanted.items():
            eng = self.engines.get(lane_id)
            if eng is None:
                eng = AutoTradeEngine(self.state, self.bridge, self.settings, lane=spec, account_id=self.account_id)
                self._wire(eng, lane_id)
                self.engines[lane_id] = eng
            else:
                eng.update_lane(spec)
            eng.set_governor(self.gov_cfg, self.ext)
        reply(True, {'lanes': sorted(self.engines)})
    def _apply_governor(self, args) -> None:
        # ***<module>.Runtime._apply_governor: Failure: Compilation Error
        from armada.governor import External
        from armada.model import GovernorConfig
        g = args.get('governor')
        if isinstance(g, dict):
            self.gov_cfg = GovernorConfig(max_positions=max(1, int(g.get('max_positions', 5))), max_daily_loss=int(g.get('max_daily_loss', 100)), block_correlated=g.get('block_correlated', True), max_lanes_per_account=g.get('max_lanes_per_account', 3))
        if 'external' in args:
            self.ext = External.from_dict(args.get('external'))
    def op_governor(self, args, reply) -> None:
        self._apply_governor(args)
        for eng in self.engines.values():
            eng.set_governor(self.gov_cfg, self.ext)
        reply(True)
    def _wire(self, eng, lane_id: str) -> None:
        e = self.emit
        eng.running_changed.connect(lambda r: e(lane_id, P.EV_RUNNING, {'running': bool(r)}))
        eng.status_changed.connect(lambda k, t: e(lane_id, P.EV_STATUS, {'kind': k, 'text': t}))
        eng.log_line.connect(lambda h, lv: e(lane_id, P.EV_LOG, {'line': h, 'level': lv}))
        eng.stats_changed.connect(lambda d: e(lane_id, P.EV_STATS, d))
        eng.tick_changed.connect(lambda d: e(lane_id, P.EV_TICK, d))
        eng.tokens_changed.connect(lambda d: e(lane_id, P.EV_TOKENS, d))
        eng.management_changed.connect(lambda d: e(lane_id, P.EV_MGMT, d))
        eng.signal_changed.connect(lambda d: e(lane_id, P.EV_SIGNAL, d))
        eng.pipeline_step.connect(lambda n, s, note: e(lane_id, P.EV_PIPE, {'node': n, 'state': s, 'note': note}))
        eng.thinking_changed.connect(lambda on: e(lane_id, P.EV_THINKING, {'on': bool(on)}))
        eng.order_opened.connect(lambda d: e(lane_id, P.EV_ORDER, d))
        eng.trade_closed.connect(lambda p, s: e(lane_id, P.EV_CLOSED, {'profit': p, 'strategy': s}))
        eng.governor_blocked.connect(lambda r: e(lane_id, P.EV_GOV, {'reason': r}))
    def op_lane_start(self, args, reply) -> None:
        eng = self.engines.get(str(args.get('lane')))
        if eng is None:
            reply(True, {'error': 'lane tidak dikenal di worker'})
            return
        else:
            reply(True, {'error': eng.start()})
    def op_lane_stop(self, args, reply) -> None:
        eng = self.engines.get(str(args.get('lane')))
        if eng is not None:
            eng.stop(close_positions=bool(args.get('close', True)))
        reply(True)
    def op_history(self, args, reply) -> None:
        from datetime import datetime
        def work():
            import MetaTrader5 as mt5
            from trading.history_data import fetch_mt5_trades
            from trading.recorder import recorder
            try:
                recorder.resolve_outcomes(mt5)
            except Exception:
                pass
            return fetch_mt5_trades(datetime.fromisoformat(args['start']), datetime.fromisoformat(args['end']))
        self._task(work, reply)
    def op_probe(self, args, reply) -> None:
        from datetime import datetime
        def work():
            from trading.history_data import probe_changes
            return probe_changes(datetime.fromisoformat(args['start']))
        self._task(work, reply)
    def op_open(self, _args, reply) -> None:
        def work():
            from trading.history_data import fetch_open_positions
            return fetch_open_positions()
        self._task(work, reply)
    def op_validate(self, args, reply) -> None:
        def work():
            from trading.settings import SettingsError
            try:
                self.settings.build_params(str(args.get('symbol') or ''), args.get('data'), args.get('overrides'))
            except SettingsError as e:
                return {'error': str(e)}
            return {'error': None}
        self._task(work, reply)
    def op_price(self, args, reply) -> None:
        def work():
            from trading.settings import live_price_point
            return live_price_point(str(args.get('symbol') or ''))
        self._task(work, reply)
    def op_shutdown(self, _args, reply) -> None:
        reply(True)
        self.quit()
    def quit(self) -> None:
        if self._quitting:
            return
        else:
            self._quitting = True
            for eng in self.engines.values():
                eng.shutdown()
            self._health.stop()
            self._acct_timer.stop()
            self._lic_timer.stop()
            from core.qt import QCoreApplication
            QCoreApplication.quit()
def _read_stdin(runtime: Runtime) -> None:
    stream = sys.stdin.buffer
    while True:
        raw = stream.readline()
        if not raw:
            break
        else:
            runtime.hooks.line_in.emit(raw.decode('utf-8', errors='replace'))
    runtime.hooks.eof.emit()
def main(argv: list[str] | None=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    account_id = 'main'
    if '--account' in argv:
        account_id = argv[argv.index('--account') + 1]
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    os.environ['KINGAI_ACCOUNT_ID'] = account_id
    plugin = None
    if os.environ.get('KINGAI_WORKER_PLUGIN'):
        plugin = importlib.import_module(os.environ['KINGAI_WORKER_PLUGIN'])
        if hasattr(plugin, 'install'):
            plugin.install()
    from core.qt import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    runtime = Runtime(account_id, out)
    if plugin is not None and hasattr(plugin, 'setup'):
            plugin.setup(runtime)
    threading.Thread(target=_read_stdin, args=(runtime,), daemon=True, name='KingAI-worker-stdin').start()
    runtime.send(P.encode({'t': 'ready', 'pid': os.getpid(), 'account': account_id, 'at': time.time()}))
    return app.exec_()
if __name__ == '__main__':
    sys.exit(main())