# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\llm\\endpoints.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

# ***<module>: Failure: Compilation Error
"""\nendpoints.py\n============\nSumber model AI yang bisa dipakai KingAI, disimpan di data/llm/endpoints.json:\n\n    endpoints   daftar endpoint (OpenRouter, 9router, Claude, OpenAI, Gemini,\n                DeepSeek, xAI, Custom). API key dienkripsi DPAPI\n                (core/secure_store.py). Instalasi baru mulai KOSONG - pengguna\n                menambah endpoint sendiri di Pengaturan › Endpoint AI.\n    routing     endpoint + model untuk fitur \"autotrade\".\n    fallback    rantai cadangan [(endpoint, model)] saat model utama kena\n                limit / error - boleh lintas endpoint.\n    budget      batas token harian (0 = tanpa batas) dan tindakan saat\n                tercapai (\"free\" pindah ke model gratis, \"stop\").\n\nSemua provider kecuali Anthropic berbicara format OpenAI-compatible\n(`/chat/completions`, `/models`); Anthropic memakai SDK resmi lewat\nllm/anthropic_adapter.py. Diambil dari QueenAI (logika sama persis).\n"""
from __future__ import annotations
import json
import threading
import time
from dataclasses import dataclass, field
from core import secure_store
from core.config import DATA_ROOT, OPENROUTER_BASE_URL
STORE_PATH = DATA_ROOT / 'data' / 'llm' / 'endpoints.json'
KIND_OPENAI = 'openai'
KIND_ANTHROPIC = 'anthropic'
BUILTIN_ID = 'openrouter'
FEATURES = ('autotrade',)
@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    tag: str
    color: str
    base_url: str
    kind: str
    key_required: bool
    note: str
# return {p.key: p for p in endpoints.json}
PROVIDERS: dict[str, Provider] = {
    'openrouter': Provider('openrouter', 'OpenRouter', 'OR', '#9aa3ff', OPENROUTER_BASE_URL, KIND_OPENAI, True, 'Agregator ratusan model, satu API key'),
    'ninerouter': Provider('ninerouter', '9router', '9R', '#2fe07a', 'http://localhost:20128/v1', KIND_OPENAI, False, 'Router lokal, OpenAI-compatible, kombinasi & fallback'),
    'anthropic': Provider('anthropic', 'Claude (Anthropic)', 'AN', '#e0876a', 'https://api.anthropic.com', KIND_ANTHROPIC, True, 'Langsung ke Anthropic, Messages API + prompt caching'),
    'openai': Provider('openai', 'OpenAI', 'OA', '#e9f2ff', 'https://api.openai.com/v1', KIND_OPENAI, True, 'Langsung ke OpenAI'),
    'gemini': Provider('gemini', 'Google Gemini', 'GM', '#7fb0ff', 'https://generativelanguage.googleapis.com/v1beta/openai', KIND_OPENAI, True, 'Langsung ke Google (mode OpenAI-compatible)'),
    'deepseek': Provider('deepseek', 'DeepSeek', 'DS', '#6d8cff', 'https://api.deepseek.com/v1', KIND_OPENAI, True, 'Langsung ke DeepSeek'),
    'xai': Provider('xai', 'xAI', 'X', '#e8e8e8', 'https://api.x.ai/v1', KIND_OPENAI, True, ''),
    'custom': Provider('custom', 'Custom', 'C', '#7a6a70', 'http://localhost:8080/v1', KIND_OPENAI, False, 'OpenAI-compatible: Ollama, LM Studio, vLLM, proxy sendiri'),
}
@dataclass
class Endpoint:
    id: str
    provider: str
    name: str
    base_url: str
    key_enc: str = ''
    models: list[str] = field(default_factory=list)
    prices: dict[str, list[float]] = field(default_factory=dict)
    @property
    def kind(self) -> str:
        return PROVIDERS.get(self.provider, PROVIDERS['custom']).kind
    @property
    def builtin(self) -> bool:
        return self.id == BUILTIN_ID
    def host(self) -> str:
        return self.base_url.split('://', 1)[(-1)].split('/', 1)[0]
    def model_list(self) -> list[str]:
        return self.models or DEFAULT_MODELS.get(self.provider, [])
    def to_json(self) -> dict:
        # ***<module>.Endpoint.to_json: Failure: Different bytecode
        return {'id': self.id, 'provider': self.provider, 'name': self.name, 'base_url': self.base_url, 'key_enc': self.key_enc, 'models': self.models, 'prices': self.prices}
@dataclass(frozen=True)
class Target:
    """Satu tujuan panggilan: endpoint + model, siap dipakai klien HTTP."""
    endpoint_id: str
    model: str
    base_url: str
    api_key: str
    kind: str
    @property
    def is_anthropic(self) -> bool:
        return self.kind == KIND_ANTHROPIC
def _builtin_row() -> dict:
    return Endpoint(BUILTIN_ID, 'openrouter', 'OpenRouter', OPENROUTER_BASE_URL).to_json()
def _default_data() -> dict:
    # ***<module>._default_data: Failure: Compilation Error
    return {
        'endpoints': [],
        'routing': {feature: None for feature in FEATURES},
        'fallback': [],
        'auto_switch': False,
        'budget': {'autotrade': 0},
        'on_limit': 'free',
    }
class EndpointStore:
    """Satu instance per aplikasi (lihat store()). Thread-safe untuk baca\n    dari worker thread; penulisan hanya dari thread UI."""
    def __init__(self, path=STORE_PATH):
        self.path = path
        self._lock = threading.RLock()
        self.app_state = None
        self.data = _default_data()
        self.load()
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raw = {}
        data = _default_data()
        if isinstance(raw, dict):
            for key in data:
                if key in raw:
                    data[key] = raw[key]
        data['endpoints'] = [e for e in data['endpoints'] if isinstance(e, dict) and e.get('id')]
        for f in FEATURES:
            data['routing'].setdefault(f, None)
        with self._lock:
            self.data = data
    def save(self) -> None:
        with self._lock:
            text = json.dumps(self.data, indent=2, ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(text, encoding='utf-8')
        except OSError:
            return None
    def endpoints(self) -> list[Endpoint]:
        # ***<module>.EndpointStore.endpoints: Failure: Compilation Error
        if getattr(self.app_state, 'api_key', '') and (not self.has_builtin()):
                self.ensure_builtin()
        with self._lock:
            return [Endpoint(**{k: e.get(k, v) for k, v in _EP_DEFAULTS.items()}, id=e['id']) for e in self.data['endpoints']]
    def has_builtin(self) -> bool:
        with self._lock:
            return any((e['id'] == BUILTIN_ID for e in self.data['endpoints']))
    def ensure_builtin(self) -> None:
        """Pasang endpoint OpenRouter bawaan (key = AppState.api_key)."""
        with self._lock:
            if any((e['id'] == BUILTIN_ID for e in self.data['endpoints'])):
                return
            else:
                self.data['endpoints'].insert(0, _builtin_row())
        self.save()
    def get(self, endpoint_id: str) -> Endpoint | None:
        return next((e for e in self.endpoints() if e.id == endpoint_id), None)
    def upsert(self, ep: Endpoint, api_key: str | None=None) -> Endpoint:
        """Tambah/ubah endpoint. `api_key` None = key lama dipertahankan."""
        if api_key is not None and (not ep.builtin):
                ep.key_enc = secure_store.protect(api_key) if api_key else ''
        if not ep.id:
            ep.id = f'{ep.provider}-{int(time.time() * 1000) % 10000000}'
        with self._lock:
            rows = self.data['endpoints']
            for i, row in enumerate(rows):
                if row['id'] == ep.id:
                    rows[i] = ep.to_json()
                    break
            else:
                rows.append(ep.to_json())
        self.save()
        return ep
    def remove(self, endpoint_id: str) -> None:
        if endpoint_id == BUILTIN_ID:
            return
        else:
            with self._lock:
                self.data['endpoints'] = [e for e in self.data['endpoints'] if e['id'] != endpoint_id]
                self.data['fallback'] = [f for f in self.data['fallback'] if f.get('endpoint') != endpoint_id]
                for f in FEATURES:
                    if (self.data['routing'].get(f) or {}).get('endpoint') == endpoint_id:
                        self.data['routing'][f] = None
        self.save()
    def api_key(self, ep: Endpoint) -> str:
        if ep.builtin:
            return getattr(self.app_state, 'api_key', '') or ''
        else:
            return secure_store.unprotect(ep.key_enc) if ep.key_enc else ''
    def set_models(self, endpoint_id: str, models: list[str]) -> None:
        with self._lock:
            for row in self.data['endpoints']:
                if row['id'] == endpoint_id:
                    row['models'] = sorted(set(models))
        self.save()
    def route(self, feature: str) -> dict | None:
        with self._lock:
            r = self.data['routing'].get(feature)
            return dict(r) if r else None
    def set_route(self, feature: str, endpoint_id: str | None, model: str='', reasoning: dict | None=None) -> None:
        """`reasoning` - thinking/effort (llm/reasoning.py), None = bawaan model."""
        with self._lock:
            route = {'endpoint': endpoint_id, 'model': model} if endpoint_id else None
            if route is not None and reasoning:
                    route['reasoning'] = reasoning
            self.data['routing'][feature] = route
        self.save()
    def fallback(self) -> list[dict]:
        with self._lock:
            return [dict(f) for f in self.data['fallback'] if self.get(f.get('endpoint', ''))]
    def set_fallback(self, chain: list[dict]) -> None:
        with self._lock:
            self.data['fallback'] = [{'endpoint': f['endpoint'], 'model': f['model']} for f in chain]
        self.save()
    def setting(self, key: str):
        with self._lock:
            return self.data.get(key)
    def set_setting(self, key: str, value) -> None:
        with self._lock:
            self.data[key] = value
        self.save()
    def target(self, endpoint_id: str, model: str) -> Target | None:
        ep = self.get(endpoint_id or BUILTIN_ID)
        if ep is None:
            return
        else:
            return Target(ep.id, model, local_url(ep.base_url), self.api_key(ep), ep.kind)
    def feature_target(self, feature: str, legacy_model: str='') -> Target | None:
        """Tujuan untuk satu fitur. Tanpa rute tersimpan: OpenRouter bawaan\n        dengan `legacy_model` (model lama di AppState) supaya perilaku\n        sebelum 4.1.2 tidak berubah."""
        r = self.route(feature)
        if r and r.get('model'):
            return self.target(r['endpoint'], r['model'])
        else:
            return self.target(BUILTIN_ID, legacy_model) if legacy_model else None
    def target_ready(self, target: Target) -> bool:
        """Model terisi dan API key ada kalau provider-nya mewajibkan."""
        ep = self.get(target.endpoint_id)
        if ep is None or not target.model:
            return False
        else:
            needs_key = ep.builtin or PROVIDERS.get(ep.provider, PROVIDERS['custom']).key_required
            return bool(target.api_key) or not needs_key
    def fallback_targets(self, exclude: Target | None=None) -> list[Target]:
        out = []
        for f in self.fallback():
            t = self.target(f['endpoint'], f['model'])
            if t is not None and (not (exclude and t.endpoint_id == exclude.endpoint_id and (t.model == exclude.model))):
                    out.append(t)
        return out
    def price(self, endpoint_id: str, model: str) -> list[float] | None:
        ep = self.get(endpoint_id)
        if ep is None:
            return
        else:
            return ep.prices.get(model)
_EP_DEFAULTS = {'provider': 'custom', 'name': '', 'base_url': '', 'key_enc': '', 'models': [], 'prices': {}}
_STORE: EndpointStore | None = None
def store() -> EndpointStore:
    global _STORE
    if _STORE is None:
        _STORE = EndpointStore()
    return _STORE
def is_anthropic_url(base_url: str) -> bool:
    return 'api.anthropic.com' in (base_url or '')
_LOCAL_HOSTS: dict[str, str] = {}
def local_url(base_url: str) -> str:
    """`http://localhost:PORT/...` -> `http://127.0.0.1:PORT/...` kalau server\n    lokal itu (9router, Ollama, ...) memang menerima IPv4. Windows mencoba\n    `::1` dulu dan mengulang koneksi yang ditolak ~2 detik sebelum jatuh ke\n    IPv4, jadi tiap permintaan ke localhost bisa telat 2+ detik. Hasil cek\n    di-cache per host:port; server yang hanya dengar di IPv6 tetap pakai\n    localhost."""
    base_url = (base_url or '').rstrip('/')
    head, sep, rest = base_url.partition('://')
    if not sep:
        return base_url
    else:
        hostport, slash, path = rest.partition('/')
        host, _, port = hostport.partition(':')
        if host.lower() != 'localhost':
            return base_url
        else:
            cached = _LOCAL_HOSTS.get(hostport.lower())
            if cached is None:
                import socket
                cached = 'localhost'
                try:
                    with socket.create_connection(('127.0.0.1', int(port or (443 if head == 'https' else 80))), timeout=0.3):
                        cached = '127.0.0.1'
                except (OSError, ValueError):
                    pass
                _LOCAL_HOSTS[hostport.lower()] = cached
            if cached == 'localhost':
                return base_url
            else:
                return f"{head}://127.0.0.1{(':' + port if port else '')}{slash}{path}"
def display_model(model: str) -> str:
    return (model or '').split('/')[(-1)].replace(':free', '')