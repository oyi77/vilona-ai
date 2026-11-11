# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\core\\worker.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nworker.py\n=========\nJalankan fungsi blocking (MT5, jaringan, AI) di thread terpisah; hasilnya\nkembali ke thread UI lewat Qt Signal (QTimer dari thread lain tidak aman).\n\n    run_task(parent, fn, arg1, on_done=..., on_failed=...)   # fn(progress, arg1)\n"""
import threading
import traceback
from core.qt import QObject, Signal
class Task(QObject):
    progress = Signal(object)
    done = Signal(object)
    failed = Signal(str)
    _alive: set = set()
    def start(self, fn, *args, **kwargs) -> None:
        Task._alive.add(self)
        self.done.connect(self._release)
        self.failed.connect(self._release)
        def run():
            # ***<module>.Task.start.run: Failure: Different control flow
            try:
                result = fn(self.progress.emit, *args, **kwargs)
            except Exception as e:
                traceback.print_exc()
                _safe_emit(self.failed, str(e) or e.__class__.__name__)
            _safe_emit(self.done, result)
        threading.Thread(target=run, daemon=True).start()
    def _release(self, _value=None) -> None:
        Task._alive.discard(self)
def run_task(_parent, fn, *args, on_done=None, on_failed=None, on_progress=None) -> Task:
    task = Task()
    if on_progress:
        task.progress.connect(on_progress)
    if on_done:
        task.done.connect(on_done)
    if on_failed:
        task.failed.connect(on_failed)
    task.start(fn, *args)
    return task
def _safe_emit(signal, value) -> None:
    try:
        signal.emit(value)
    except RuntimeError:
        return None