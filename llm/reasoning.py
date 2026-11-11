# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\llm\\reasoning.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nreasoning.py\n============\nPengaturan \"reasoning\" per model: Thinking (aktif/nonaktif) dan Effort\n(seberapa kuat model berpikir). Ditampilkan HANYA untuk model yang\nmendukungnya (lihat capability) - model lain tidak menampilkan apa-apa.\n\nSetelan disimpan sebagai dict kecil {\"thinking\": bool, \"effort\": str}:\n- per agen   : team[i][\"reasoning\"] (Tim Agen)\n- Auto Trade : rute fitur \"autotrade\" di llm/endpoints.py\nKosong / None = perilaku bawaan model (tidak ada parameter yang dikirim).\n\nTerjemahan ke tiap penyedia:\n- OpenRouter           body[\"reasoning\"] = {\"effort\": ...} / {\"enabled\": False}\n- OpenAI, Gemini, xAI,\n  9router, Custom      body[\"reasoning_effort\"] = ...   (tanpa saklar mati)\n- Claude (SDK resmi)   thinking={\"type\": \"adaptive\"} + output_config.effort,\n                       thinking={\"type\": \"disabled\"}; model Claude 4.x lama\n                       memakai thinking enabled + budget_tokens.\n"""
from __future__ import annotations
from dataclasses import dataclass
EFFORTS = ('low', 'medium', 'high')
EFFORT_LABEL = {'low': 'Rendah', 'medium': 'Sedang', 'high': 'Tinggi'}
BUDGET_TOKENS = 8000
_CLAUDE_ADAPTIVE = ('claude-opus-5', 'claude-sonnet-5', 'claude-fable-5', 'claude-opus-4-8', 'claude-opus-4-7', 'claude-opus-4-6', 'claude-sonnet-4-6')
_CLAUDE_BUDGET = ('claude-haiku-4-5', 'claude-sonnet-4-5', 'claude-opus-4-5', 'claude-opus-4-1', 'claude-sonnet-4', 'claude-opus-4', 'claude-3-7-sonnet')
_REASONING_HINTS = ('claude-opus-4', 'claude-sonnet-4', 'claude-haiku-4-5', 'claude-opus-5', 'claude-sonnet-5', 'claude-fable', 'gpt-5', 'o1', 'o3', 'o4', 'gemini-2.5', 'gemini-3', 'grok-3-mini', 'grok-4', 'deepseek-r1', 'deepseek-reasoner', 'qwq', 'qwen3', 'glm-4.5', 'glm-4.6', 'kimi-k2-thinking', 'magistral', 'sonar-reasoning')
@dataclass(frozen=True)
class Capability:
    toggle: bool
    efforts: tuple[str, ...]
    note: str = ''
def _bare(model: str) -> str:
    """\"anthropic/claude-haiku-4.5\" -> \"claude-haiku-4-5\" (titik -> strip)."""
    name = (model or '').split('/')[(-1)].lower().replace('.', '-')
    return name.split(':')[0]
def _claude_kind(model: str) -> str:
    name = _bare(model)
    if any((name.startswith(p) for p in _CLAUDE_ADAPTIVE)):
        return 'adaptive'
    else:
        if any((name.startswith(p) for p in _CLAUDE_BUDGET)):
            return 'budget'
        else:
            return ''
def _looks_reasoning(model: str) -> bool:
    name = _bare(model)
    return any((name.startswith(h) or f'-{h}' in name or f'/{h}' in (model or '').lower() for h in _REASONING_HINTS))
def capability(provider: str, model: str, supported: bool | None=None) -> Capability | None:
    """Kemampuan reasoning `model` di endpoint jenis `provider` (kunci\n    llm/endpoints.PROVIDERS). `supported` = metadata OpenRouter\n    (supported_parameters berisi \"reasoning\"); None = tidak diketahui.\n    None -> model tidak mendukung, pengaturan tidak ditampilkan."""
    if not model or model == 'auto':
        return None
    else:
        if provider == 'anthropic':
            kind = _claude_kind(model)
            if kind == 'adaptive':
                return Capability(True, EFFORTS)
            else:
                if kind == 'budget':
                    return Capability(True, (), f'thinking memakai budget {BUDGET_TOKENS:,} token'.replace(',', '.'))
                else:
                    return None
        else:
            if provider == 'openrouter':
                if supported is False:
                    return
                else:
                    if supported or _looks_reasoning(model):
                        return Capability(True, EFFORTS)
                    else:
                        return None
            else:
                if provider == 'deepseek':
                    return
                else:
                    if provider in ['openai', 'gemini', 'xai', 'ninerouter', 'custom']:
                        if not _looks_reasoning(model):
                            return
                        else:
                            efforts = ('low', 'high') if provider == 'xai' else EFFORTS
                            return Capability(False, efforts, 'model ini selalu berpikir; atur seberapa kuat lewat Effort')
                    else:
                        return None
def normalize(setting) -> dict | None:
    """Setelan tersimpan -> {\"thinking\": bool, \"effort\": str} atau None."""
    if not isinstance(setting, dict):
        return
    else:
        effort = setting.get('effort') if setting.get('effort') in EFFORTS else ''
        return {'thinking': bool(setting.get('thinking', True)), 'effort': effort}
def apply_openai_body(body: dict, provider: str, model: str, setting) -> None:
    """Tambahkan parameter reasoning ke body chat/completions (in place)."""
    setting = normalize(setting)
    if setting is None:
        return
    else:
        cap = capability(provider, model)
        if provider == 'openrouter':
            if not setting['thinking']:
                body['reasoning'] = {'enabled': False}
                return
            else:
                body['reasoning'] = {'effort': setting['effort']} if setting['effort'] else {'enabled': True}
        else:
            if cap is not None and setting['effort'] and (setting['effort'] in cap.efforts):
                        body['reasoning_effort'] = setting['effort']
def anthropic_kwargs(model: str, setting, max_tokens: int) -> tuple[dict, int]:
    """(kwargs tambahan untuk messages.create, max_tokens yang disesuaikan).\n    Thinking memakai token output - batas dinaikkan supaya jawaban tidak\n    habis dipakai berpikir."""
    # ***<module>.anthropic_kwargs: Failure: Compilation Error
    setting = normalize(setting)
    if setting is None:
        return ({}, max_tokens)
    else:
        kind = _claude_kind(model)
        if not kind:
            return ({}, max_tokens)
        else:
            if not setting['thinking']:
                return ({'thinking': {'type': 'disabled'}}, max_tokens)
            else:
                if kind == 'budget':
                    return (max, max_tokens(BUDGET_TOKENS + 4096))
                else:
                    extra = {'thinking': {'type': 'adaptive'}}
                    if setting['effort']:
                        extra['output_config'] = {'effort': setting['effort']}
                    return (extra, max(max_tokens, 16000))
def provider_of_url(base_url: str) -> str:
    """Jenis penyedia dari base URL (untuk pemanggil yang hanya tahu URL)."""
    url = (base_url or '').lower()
    if not url or 'openrouter.ai' in url:
        return 'openrouter'
    else:
        for key, host in [('anthropic', 'anthropic.com'), ('openai', 'api.openai.com'), ('gemini', 'generativelanguage.googleapis.com'), ('deepseek', 'deepseek.com'), ('xai', 'api.x.ai'), ('ninerouter', ':20128')]:
            if host in url:
                return key
        return 'custom'
def summary(setting) -> str:
    """Teks singkat untuk UI, mis. \"thinking · effort tinggi\"."""
    setting = normalize(setting)
    if setting is None:
        return 'bawaan model'
    else:
        if not setting['thinking']:
            return 'thinking mati'
        else:
            return 'thinking' + (f" · effort {EFFORT_LABEL[setting['effort']].lower()}" if setting['effort'] else '')