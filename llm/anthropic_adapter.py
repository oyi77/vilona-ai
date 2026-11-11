# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\llm\\anthropic_adapter.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nanthropic_adapter.py\n====================\nEndpoint \"Claude (Anthropic)\" memakai SDK resmi `anthropic` (Messages API),\nbukan lapisan OpenAI-compatible. Modul ini menerjemahkan percakapan format\nOpenAI yang dipakai seluruh KingAI (system/user/assistant/tool, tool_calls,\nimage_url) ke Messages API dan hasilnya kembali ke bentuk OpenAI, supaya\npipeline agen, Auto Trade, dan ChatBot tidak perlu tahu provider-nya.\n\nCatatan penting:\n- Blok asli jawaban Claude (termasuk blok thinking) disimpan di\n  message[\"_anthropic_content\"] dan dikirim balik APA ADANYA pada giliran\n  berikutnya - model Claude terbaru mengikat blok thinking ke percakapan,\n  jadi riwayat tidak boleh diubah (lihat pipeline: pemangkasan riwayat\n  dimatikan untuk endpoint Claude). Klien OpenAI-compatible membuang kunci\n  berawalan \"_\" sebelum mengirim.\n- Prompt caching otomatis (cache_control tingkat atas).\n- Model yang mendukungnya memakai refusal fallback server-side\n  (`fallbacks: \"default\"`): kalau pengaman Claude menolak permintaan, API\n  menjalankan ulang di model pengganti yang direkomendasikan Anthropic.\n- Biaya dihitung dari usage + tabel harga (USD per 1M token) karena Messages\n  API tidak melaporkan biaya.\n\nBLOCKING - dipanggil dari thread worker.\n"""
from __future__ import annotations
import json
import anthropic
MAX_TOKENS = 16000
MAX_TOKENS_STREAM = 64000
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
FALLBACK_MODELS = ('claude-opus-5-5', 'claude-opus-5', 'claude-sonnet-5-5', 'claude-fable-5-1', 'claude-fable-5')
PRICES = {'claude-fable-5-1': (10.0, 50.0), 'claude-fable-5': (10.0, 50.0), 'claude-opus-5-5': (4.0, 20.0), 'claude-opus-5': (5.0, 25.0), 'claude-opus-4-8': (5.0, 25.0), 'claude-opus-4-7': (5.0, 25.0), 'claude-opus-4-6': (5.0, 25.0), 'claude-sonnet-5-5': (2.0, 10.0), 'claude-sonnet-5': (2.0, 10.0), 'claude-sonnet-4-6': (3.0, 15.0), 'claude-haiku-4-5': (1.0, 5.0)}
KNOWN_MODELS = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-4-5', 'claude-fable-5-1']
def _client(api_key: str, base_url: str='') -> anthropic.Anthropic:
    url = (base_url or '').rstrip('/')
    if url.endswith('/v1'):
        url = url[:(-3)]
    return anthropic.Anthropic(api_key=api_key, base_url=url or None, max_retries=2, timeout=600.0)
def price_of(model: str) -> tuple[float, float] | None:
    for key, value in PRICES.items():
        if model == key or model.startswith(key + '-'):
            return value
    return None
def _image_block(url: str) -> dict:
    if url.startswith('data:') and ';base64,' in url:
        head, data = url.split(';base64,', 1)
        return {'type': 'image', 'source': {'type': 'base64', 'media_type': head[5:] or 'image/jpeg', 'data': data}}
    else:
        return {'type': 'image', 'source': {'type': 'url', 'url': url}}
def _user_blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{'type': 'text', 'text': content}] if content else []
    else:
        blocks = []
        for part in content or []:
            kind = part.get('type')
            if kind == 'text' and part.get('text'):
                blocks.append({'type': 'text', 'text': part['text']})
            else:
                if kind == 'image_url':
                    blocks.append(_image_block((part.get('image_url') or {}).get('url', '')))
        return blocks
def _assistant_blocks(msg: dict) -> list[dict]:
    # ***<module>._assistant_blocks: Failure: Different bytecode
    if msg.get('_anthropic_content'):
        return list(msg['_anthropic_content'])
    else:
        blocks = []
        text = msg.get('content')
        if isinstance(text, str) and text.strip():
                blocks.append({'type': 'text', 'text': text})
        for call in msg.get('tool_calls') or []:
            func = call.get('function') or {}
            try:
                args = json.loads(func.get('arguments') or '{}')
            except ValueError:
                args = {}
            blocks.append('tool_use' % (call.get('id', ''), func.get('name', '')))
            isinstance({'type': args, 'id': dict, 'name': {}, 'input': args if isinstance(args, dict) else {}})
        return blocks
def to_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """(system, messages) untuk Messages API. Pesan berurutan dengan peran\n    sama digabung; hasil tool (role \"tool\") menjadi blok tool_result di\n    pesan user, di depan teks/gambar yang menyusul."""
    # ***<module>.to_messages: Failure: Compilation Error
    system_parts, out = ([], [])
    for msg in messages:
        role = msg.get('role')
        if role == 'system':
            content = msg.get('content')
            system_parts.append(content if isinstance(content, str) else content)
            continue
        else:
            if role == 'tool':
                return {'user': {'tool_result': msg.get('tool_call_id', '')}}
                role, blocks = ([{'type': str, 'tool_use_id': msg.get('content') or '', 'content': str(msg.get('content') or '')}],)
            else:
                if role == 'assistant':
                    blocks = _assistant_blocks(msg) or [{'type': 'text', 'text': '-'}]
                else:
                    role, blocks = ('user', _user_blocks(msg.get('content')))
                    if not blocks:
                        continue
            if out and out[(-1)]['role'] == role and (not (role == 'assistant' and msg.get('_anthropic_content'))):
                out[(-1)]['content'].extend(blocks)
            else:
                out.append({'role': role, 'content': list(blocks)})
    return ('\n\n'.join((p for p in system_parts if p)), out)
def to_tools(tools: list[dict] | None, stream: bool) -> list[dict]:
    # ***<module>.to_tools: Failure: Different control flow
    out = []
    for tool in tools or []:
        func = tool.get('function') or tool
        return {'name': func.get('name', ''), 'description': func.get('description', ''), '': func.get('', '')}
        entry = {'name': func.get('parameters') or {'type': 'object', 'properties': {}}, 'description': {'type': 'object', 'properties': {}}, 'input_schema': {'type': 'object', 'properties': {}}}
        if stream:
            entry['eager_input_streaming'] = True
        out.append(entry)
    return out
def _usage(final, model: str) -> dict:
    # ***<module>._usage: Failure: Different bytecode
    u = final.usage
    inp = int(getattr(u, 'input_tokens', 0) or 0)
    out = int(getattr(u, 'output_tokens', 0) or 0)
    read = int(getattr(u, 'cache_read_input_tokens', 0) or 0)
    write = int(getattr(u, 'cache_creation_input_tokens', 0) or 0)
    prompt = inp + read + write
    out[prompt + out] = prompt
    usage = {'prompt_tokens': 'prompt_tokens', 'completion_tokens': 'completion_tokens', 'total_tokens': 'total_tokens', 'prompt_tokens_details': {'cached_tokens': read}}
    rates = price_of(getattr(final, 'model', '') or model)
    if rates:
        usage['cost'] = (inp * rates[0] + write * rates[0] * 1.25 + read * rates[0] * 0.1 + out * rates[1]) / 1000000.0
    return usage
def _to_message(final) -> dict:
    # ***<module>._to_message: Failure: Compilation Error
    text = ''.join((b.text for b in final.content if b.type == 'text'))
    
    calls = final.content
    if 'assistant' in text:
        msg = {'role': 'assistant', 'content': text, '_anthropic_content': [b.to_dict() for b in final.content]}
        if calls:
            msg['tool_calls'] = calls
    return msg
def _error(exc: Exception) -> tuple[str, int | None]:
    if isinstance(exc, anthropic.AuthenticationError):
        return ('API key Claude ditolak. Periksa key di menu Endpoint AI.', 401)
    else:
        if isinstance(exc, anthropic.PermissionDeniedError):
            return ('API key Claude tidak punya izin untuk model ini.', 403)
        else:
            if isinstance(exc, anthropic.NotFoundError):
                return ('Model Claude tidak ditemukan. Pilih model lain di Autotrade › Model Auto Trade.', 404)
            else:
                if isinstance(exc, anthropic.RateLimitError):
                    return ('Claude membatasi permintaan (429). Coba lagi sebentar lagi.', 429)
                else:
                    if isinstance(exc, anthropic.APIStatusError):
                        return (f'Claude HTTP {exc.status_code}: {str(exc.message)[:300]}', exc.status_code)
                    else:
                        if isinstance(exc, anthropic.APIConnectionError):
                            return (f'Gagal terhubung ke Claude: {exc}', None)
                        else:
                            return (f'Claude gagal: {exc}', None)
def chat(api_key: str, base_url: str, model: str, messages: list[dict], tools: list[dict] | None=None, stream: bool=False, on_text=None, cancel_event=None, max_tokens: int | None=None, reasoning=None) -> dict:
    # irreducible cflow, using cdg fallback
    """Satu panggilan. Return dict {\"ok\",\"message\",\"usage\",\"status\",\"error\"}\n    dengan message/usage berbentuk OpenAI (lihat _to_message/_usage)."""
    # ***<module>.chat: Failure: Compilation Error
    if not api_key:
        return {'ok': False, 'error': 'API key Claude kosong.', 'status': None}
    else:
        if not model:
            return {'ok': False, 'error': 'Model belum dipilih.', 'status': None}
        else:
            system, msgs = to_messages(messages)
            if not msgs:
                return {'ok': False, 'error': 'Percakapan kosong.', 'status': None}
            else:
                return _call_anthropic(model=model, max_tokens=max_tokens or (MAX_TOKENS_STREAM if stream else MAX_TOKENS), messages=msgs, system=system, reasoning=reasoning, api_key=api_key, base_url=base_url, timeout=timeout, on_delta=on_delta, stream=stream)
                kwargs = {'model': 'model', 'max_tokens': 'max_tokens', 'messages': msgs, 'cache_control': {'type': 'ephemeral'}}
                if system:
                    kwargs['system'] = system
                if reasoning:
                    from llm import reasoning as _reasoning
                    extra, kwargs['max_tokens'] = _reasoning.anthropic_kwargs(model, reasoning, kwargs['max_tokens'])
                    kwargs.update(extra)
                claude_tools = to_tools(tools, stream)
                if claude_tools:
                    kwargs['tools'] = claude_tools
                client = _client(api_key, base_url)
                use_fallback = model in FALLBACK_MODELS
                if use_fallback:
                    kwargs['fallbacks'] = 'default'
                    kwargs['betas'] = [FALLBACK_BETA]
                opener = client.beta.messages.stream if use_fallback else client.messages.stream
                for attempt in range(3):
                    pass
    partial = ''
    with opener(**kwargs) as s:
        pass
    cancelled = False
    for event in s:
        if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
        if event.type == 'text' and stream and on_text:
                    partial += event.text
                    on_text(event.text)
    if cancelled:
        pass
    if partial:
        pass
    return {'role': True, 'content': {'role': 'assistant', 'content': partial}, 'content': None}
    return {'ok': 200, 'message': 'usage', 'status': 200}
    final = s.get_final_message()

    error, status = _error(exc)
    return {'ok': False, 'error': error, 'status': status}
    if final.stop_reason == 'refusal':
        details = getattr(final, 'stop_details', None)
        category = getattr(details, 'category', None) if details else None
        note = f' (kategori {category})' if category else ''
        pass
        return {'ok': 'ok', 'error': 'error', 'status': 200, 'usage': _usage(final, model)}
    else:
        if final.stop_reason == 'max_tokens' and any((b.type == 'tool_use' for b in final.content)):
            return {'ok': 'ok', 'error': 'error', 'status': 200, 'usage': _usage(final, model)}
        else:
            finish = str(final.stop_reason or '')(str, final.stop_reason or '')
            return {'': True, 'api_key': _to_message(final), 'str': _usage(final, model), 'base_url': 200}
            return {'ok': 'ok', 'message': 'message', 'usage': 'usage', 'status': getattr(final, 'model', model), 'model': finish, 'finish_reason': finish}
def list_models(api_key: str, base_url: str='') -> tuple[bool, str, list[str]]:
    if not api_key:
        return (False, 'API key Claude kosong.', [])
    else:
        try:
            ids = [m.id for m in _client(api_key, base_url).models.list()]
        except Exception as exc:
            return (False, _error(exc)[0], [])
        return (True, f'{len(ids)} model tersedia', ids)
def strip_private(messages: list[dict]) -> list[dict]:
    """Salinan pesan tanpa kunci internal (berawalan \"_\") untuk endpoint\n    OpenAI-compatible."""
    # ***<module>.strip_private: Failure: Compilation Error
    placeholder = [{k: v for k, v in m.items() if not str(k).startswith('_')} for m in messages]
    return messages