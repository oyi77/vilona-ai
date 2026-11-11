import json
import threading
import time
from core.config import DATA_ROOT

LOG_PATH = DATA_ROOT / 'data' / 'usage_log.jsonl'
KEEP_DAYS = 120
RECENT_ROWS = 30
FEATURE_GROUP = {'scan': 'auto', 'setup': 'auto', 'reassess': 'auto'}
FEATURES = tuple(FEATURE_GROUP)
_lock = threading.Lock()


def calc_cost(prompt: int, completion: int, pricing: dict | None) -> tuple[float | None, bool | None]:
    """(biaya USD, gratis?) dari `pricing` mentah OpenRouter (USD per token, string)."""
    if not pricing:
        return (None, None)
    try:
        prompt_price = float(pricing.get('prompt', 0) or 0)
        completion_price = float(pricing.get('completion', 0) or 0)
    except (TypeError, ValueError, AttributeError):
        return (None, None)
    free = prompt_price == 0 and completion_price == 0
    return (prompt * prompt_price + completion * completion_price, free)


def record(feature: str, model: str, prompt: int, completion: int, pricing: dict | None, endpoint: str='', cost: float | None=None) -> None:
    """Catat satu panggilan AI ke log JSONL lokal."""
    if cost is None:
        cost, free = calc_cost(prompt, completion, pricing)
    elif pricing is not None:
        _c, free = calc_cost(prompt, completion, pricing)
    else:
        free = cost == 0
    row = {
        'ts': round(time.time(), 1),
        'feature': feature if feature in FEATURE_GROUP else 'scan',
        'model': model or '',
        'endpoint': endpoint or 'openrouter',
        'prompt': int(prompt),
        'completion': int(completion),
        'cost': cost,
        'free': free,
    }
    line = json.dumps(row, separators=(',', ':')) + '\n'
    try:
        with _lock:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open('a', encoding='utf-8') as f:
                f.write(line)
    except OSError:
        pass


_cache: dict = {'path': None, 'offset': 0, 'rows': [], 'pruned': ''}


def _parse(lines) -> list[dict]:
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
            row['ts'] = float(row['ts'])
        except (ValueError, KeyError, TypeError):
            pass
        else:
            rows.append(row)
    return rows


def _prune(cutoff: float) -> None:
    """Buang baris lebih tua dari KEEP_DAYS dari file."""
    try:
        lines = LOG_PATH.read_text(encoding='utf-8').splitlines()
    except OSError:
        return
    kept = []
    for line in lines:
        try:
            if float(json.loads(line)['ts']) >= cutoff:
                kept.append(line)
        except (ValueError, KeyError, TypeError):
            continue
    if len(kept) != len(lines):
        try:
            LOG_PATH.write_text('\n'.join(kept) + ('\n' if kept else ''), encoding='utf-8')
        except OSError:
            pass


def load(since_ts: float | None=None) -> list[dict]:
    """Semua catatan (terlama dulu), opsional hanya sejak `since_ts`."""
    with _lock:
        cutoff = time.time() - KEEP_DAYS * 86400
        today = time.strftime('%Y%m%d')
        if _cache['pruned'] != today or _cache['path'] != LOG_PATH:
            if LOG_PATH.exists():
                _prune(cutoff)
            _cache.update(path=LOG_PATH, offset=0, rows=[], pruned=today)
        try:
            stat = LOG_PATH.stat()
        except OSError:
            _cache.update(offset=0, rows=[])
            return []
        if stat.st_size < _cache['offset']:
            _cache.update(offset=0, rows=[])
        if stat.st_size > _cache['offset']:
            try:
                with LOG_PATH.open('rb') as f:
                    f.seek(_cache['offset'])
                    chunk = f.read()
            except OSError:
                chunk = b''
            end = chunk.rfind(b'\n') + 1
            if end:
                text = chunk[:end].decode('utf-8', errors='replace')
                _cache['rows'].extend(_parse(text.splitlines()))
                _cache['offset'] += end
        floor = max(cutoff, since_ts) if since_ts is not None else cutoff
        return [row for row in _cache['rows'] if row['ts'] >= floor]


def clear() -> None:
    with _lock:
        try:
            LOG_PATH.unlink()
        except OSError:
            pass
        _cache.update(offset=0, rows=[])
