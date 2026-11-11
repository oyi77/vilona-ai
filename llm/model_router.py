# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\llm\\model_router.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nmodel_router.py\n================\nLayer tipis di atas AIClient/OpenRouterClient - TIDAK memanggil HTTP sendiri,\nhanya orkestrasi PEMILIHAN model \"terbaik\" (dari data lokal yang sudah ada di\nAppState, tanpa benchmark eksternal) dan AUTO-SWITCH ke model lain saat model\naktif gagal (rate-limit/timeout/error server). Dipakai OPSIONAL oleh\npemanggil yang mau auto-switch (Auto Trade scan-loop) - ChatBot/Scan manual\ntetap bisa memanggil AIClient/OpenRouterClient langsung seperti sebelumnya\ntanpa lewat sini sama sekali (lihat app_state.auto_switch_enabled sebagai\ntoggle on/off fitur ini).\n"""
import time
class RouterError:
    """Klasifikasi error dari satu percobaan panggilan AI - dipakai\n    `next_model()` untuk memutuskan apakah & bagaimana harus ganti model.\n    `kind` salah satu: \"rate_limited\", \"timeout\", \"connection\",\n    \"server_error\", \"bad_response\", \"auth\" (401, TIDAK memicu switch)."""
    def __init__(self, kind: str, http_status: int | None, message: str=''):
        self.kind = kind
        self.http_status = http_status
        self.message = message
    @classmethod
    def from_status(cls, http_status: int | None, exception_kind: str | None=None) -> 'RouterError | None':
        """Terjemahkan (http_status, exception_kind) hasil `return_status=True`\n        dari AIClient.chat()/OpenRouterClient.scan_signal() jadi RouterError,\n        atau None kalau bukan error (status 200/sukses). `exception_kind`\n        diisi pemanggil kalau exception jaringan terjadi (bukan dari HTTP\n        status) - salah satu \"timeout\"/\"connection\"."""
        if exception_kind in ['timeout', 'connection']:
            return cls(exception_kind, None)
        else:
            if http_status is None:
                return
            if http_status == 200:
                return
            if http_status == 429:
                return cls('rate_limited', http_status)
            else:
                if http_status == 401:
                    return cls('auth', http_status)
                else:
                    if 500 <= http_status < 600:
                            return cls('server_error', http_status)
                    if http_status in [400, 422]:
                        return cls('bad_response', http_status)
                    else:
                        return cls('bad_response', http_status)
def _is_free_model(model_id: str, pricing: dict | None) -> bool:
    if model_id.endswith(':free'):
        return True
    else:
        if not pricing:
            return False
        else:
            return pricing.get('prompt', 0) == 0 and pricing.get('completion', 0) == 0
class ModelRouter:
    # ***<module>.ModelRouter: Failure: Different bytecode
    def __init__(self, app_state, models_pool: list[dict]):
        """`models_pool` - hasil AIClient.list_models() (list of dict\n        {\"id\", \"modalities\", \"pricing\"})."""
        self.app_state = app_state
        self.models_pool = models_pool or []
    def _candidates(self, free_only: bool | None, require_tools: bool, exclude: set[str]) -> list[dict]:
        pool = self.models_pool
        if free_only is None:
            free_only = self.app_state.filter_free and (not self.app_state.filter_pay)
        result = []
        for entry in pool:
            model_id = entry.get('id', '')
            if not model_id or model_id in exclude:
                continue
            else:
                is_free = _is_free_model(model_id, entry.get('pricing'))
                if free_only and (not is_free):
                        continue
                if require_tools:
                    capability = self.app_state.model_toolcall_capability.get(model_id)
                    supported_params = entry.get('supported_parameters') or []
                    known_supported = capability is True or (capability is None and 'tools' in supported_params)
                    if capability is False or not known_supported:
                        continue
                result.append(entry)
        return result
    # return None + False
    def rank_candidates(self, free_only: bool | None, require_tools: bool, exclude: set[str]=frozenset()) -> list[str]:
        """Urutkan kandidat dari yang paling \"layak\" (riwayat sukses lebih\n        banyak, belum pernah gagal baru-baru ini) ke paling tidak layak."""
        candidates = self._candidates(free_only, require_tools, set(exclude))
        def score(entry: dict) -> tuple:
            model_id = entry['id']
            usage = self.app_state.model_usage_history.get(model_id)
            usage_total = usage.get('total', 0) if usage else 0
            fail = self.app_state.model_fail_history.get(model_id)
            fail_count = fail.get('count', 0) if fail else 0
            tested = 1 if model_id in self.app_state.model_tested_history else 0
            return (-fail_count, usage_total, tested)
        return [e['id'] for e in sorted(candidates, key=score, reverse=True)]
    def pick_best(self, free_only: bool | None=None, require_tools: bool=False) -> str | None:
        """Model \"terbaik\" saat ini menurut heuristik data lokal - None\n        kalau tidak ada kandidat sama sekali yang cocok filter."""
        ranked = self.rank_candidates(free_only=free_only, require_tools=require_tools)
        return ranked[0] if ranked else None
    def next_model(self, current: str, error: RouterError, exclude: set[str]=frozenset()) -> str | None:
        """Model pengganti setelah `current` gagal dengan `error`. Kalau\n        error.kind == \"auth\", TIDAK ADA pengganti (API key invalid, ganti\n        model tidak membantu) - return None supaya pemanggil propagate error\n        apa adanya. `filter_free`-only tetap dihormati: kalau user memang\n        cuma mengizinkan model gratis, auto-switch TIDAK PERNAH melompat ke\n        model berbayar."""
        if error.kind == 'auth':
            return
        else:
            exclude_all = set(exclude) | {current}
            for backup in getattr(self.app_state, 'backup_models', []) or []:
                if backup and backup not in exclude_all:
                    return backup
            free_only = self.app_state.filter_free and (not self.app_state.filter_pay)
            ranked = self.rank_candidates(free_only=free_only, exclude=exclude_all)
            return ranked[0] if ranked else None
    def call_with_autoswitch(self, initial_model: str, call_fn, max_attempts: int=3):
        """Loop: panggil `call_fn(model)` -> call_fn HARUS return tuple yang\n        elemen TERAKHIRnya adalah `RouterError | None` (pemanggil membungkus\n        hasil AIClient/OpenRouterClient dengan RouterError.from_status\n        sebelum mengembalikan ke sini) -> kalau ada error yang trigger\n        switch, catat & pindah ke next_model(), ulangi sampai sukses atau\n        max_attempts habis. Return (hasil_call_fn_terakhir, model_dipakai,\n        list_pesan_switch)."""
        model = initial_model
        excluded = set()
        switch_logs = []
        result = None
        for attempt in range(max_attempts):
            result = call_fn(model)
            error = result[(-1)]
            if error is None:
                return (result, model, switch_logs)
            else:
                if error.kind == 'connection' and attempt == 0:
                    time.sleep(1)
                    result = call_fn(model)
                    error = result[(-1)]
                    if error is None:
                        return (result, model, switch_logs)
                if error.kind == 'auth':
                    break
                else:
                    excluded.add(model)
                    next_m = self.next_model(model, error, exclude=excluded)
                    if next_m is None:
                        break
                    else:
                        self.app_state.notify_model_switch(model, next_m, error.kind)
                        switch_logs.append((model, next_m, error.kind))
                        model = next_m
        return (result, model, switch_logs)