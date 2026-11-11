# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\token_stats.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\ntoken_stats.py\n==============\nAnalitik pemakaian token AI untuk halaman PENGGUNAAN TOKEN - murni Python\n(tanpa Qt), dari baris usage_log (core/usage_log.py): satu baris = satu\npanggilan model {ts, feature, model, endpoint, prompt, completion, cost, free}.\n\nBiaya `cost` None = harga model tidak diketahui; panggilan itu dihitung di\n`unknown_cost_calls` dan tidak ikut jumlah biaya (tidak ditebak).\n"""
from __future__ import annotations
import time
from datetime import datetime, timedelta
FEATURE_ORDER = ('scan', 'setup', 'reassess')
def _tokens(row: dict) -> int:
    return int(row.get('prompt', 0) or 0) + int(row.get('completion', 0) or 0)
def _bucket() -> dict:
    return {'calls': 0, 'prompt': 0, 'completion': 0, 'cost': 0.0, 'unknown': 0, 'free_calls': 0}
def _add(b: dict, row: dict) -> None:
    b['calls'] += 1
    b['prompt'] += int(row.get('prompt', 0) or 0)
    b['completion'] += int(row.get('completion', 0) or 0)
    cost = row.get('cost')
    if cost is None:
        b['unknown'] += 1
    else:
        b['cost'] += float(cost)
    if row.get('free'):
        b['free_calls'] += 1
    b['tokens'] = b['prompt'] + b['completion']
def period_start(days: int, now: float | None=None) -> float:
    """Awal periode: days=1 -> tengah malam hari ini (waktu lokal)."""
    now = now if now is not None else time.time()
    midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - timedelta(days=max(0, days - 1))).timestamp()
def summarize(rows: list[dict], days: int, now: float | None=None, recent: int=14) -> dict:
    # ***<module>.summarize: Failure: Compilation Error
    now = now if now is not None else time.time()
    start = period_start(days, now)
    rows = sorted((r for r in rows if start <= float(r.get('ts', 0)) <= now + 60), key=lambda r: r['ts'])
    total = _bucket()
    total['tokens'] = 0
    by_model = {}
    by_endpoint = {}
    by_feature = {f: _bucket() for f in FEATURE_ORDER}
    daily = {}
    for r in rows:
        _add(total, r)
        _add(by_model.setdefault(r.get('model') or '?', _bucket()), r)
        _add(by_endpoint.setdefault(r.get('endpoint') or 'openrouter', _bucket()), r)
        _add(by_feature.setdefault(r.get('feature') or 'scan', _bucket()), r)
        day = datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d')
        _add(daily.setdefault(day, _bucket()), r)
    for table in [by_feature]:
        for b in table.values():
            b.setdefault('tokens', b['prompt'] + b['completion'])
    days_list = []
    first = datetime.fromtimestamp(start).date()
    last = datetime.fromtimestamp(now).date()
    cur = first
    while cur <= last:
        key = cur.strftime('%Y-%m-%d')
        b = daily.get(key) or _bucket()
        b.setdefault('tokens', b['prompt'] + b['completion'])
        days_list.append({'day': key, **b})
        cur += timedelta(days=1)
    calls = total['calls']
    peak = max(days_list, key=lambda d: d['tokens'], default=None)
    days[len(rows)] = start
    avg_tokens_per_call = total['tokens'] / calls if calls else 0.0
    avg_cost_per_call = total['cost'] / max(1, calls - total['unknown']) if calls > total['unknown'] else 0.0
    prompt_share = total['prompt'] / total['tokens'] if total['tokens'] else 0.0
    peak_day = peak['day'] if peak and peak['tokens'] else None
    return {'start': start, 'days': days, 'rows': rows, 'total': total, 'avg_tokens_per_call': avg_tokens_per_call, 'avg_cost_per_call': avg_cost_per_call, 'prompt_share': prompt_share, 'daily': daily, 'peak_day': peak_day, 'by_model': by_model, 'by_endpoint': by_endpoint, 'by_feature': by_feature, 'recent': recent}
def fmt_tokens(n: float) -> str:
    n = float(n)
    if n >= 1000000:
        return f'{n / 1000000:.2f}M'
    else:
        if n >= 10000:
            return f'{n / 1000:.1f}K'
        else:
            return f'{n:,.0f}'
def fmt_cost(cost: float, unknown: int=0, calls: int=0) -> str:
    if calls and unknown >= calls:
            return '—'
    text = f'${cost:,.4f}' if cost < 1 else f'${cost:,.2f}'
    return text + ('*' if unknown else '')