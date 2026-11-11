# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\trading\\performance.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nperformance.py\n==============\nRekap Performa (Riwayat Trade › REKAP PERFORMA, 4.1.4) - murni Python.\n\nMasukan = baris trade dari trade_history_page.fetch_mt5_trades (satu posisi\n= satu baris, `pnl` sudah profit + swap + komisi), digabung buku catatan\ntiket (session_guard.load_ledger) supaya tiap posisi tahu MODEL AI yang\nmembukanya. Keluaran: angka ringkas (winrate, profit factor, max drawdown,\nexpectancy), kurva equity + drawdown, dan perbandingan per model / strategi\n/ sesi.\n\nDrawdown dihitung dari kurva equity tertutup (urut waktu tutup) mulai dari\n`start_equity`; tanpa saldo awal yang diketahui persentasenya None.\n"""
from __future__ import annotations
import math
from datetime import datetime
from trading.trading_rules import MAGIC_CODEX, MAGIC_RETIRED, is_autotrade_magic
UNKNOWN_MODEL = 'Tidak tercatat'
AI_STRATEGY = 'AI'
_AI_ALIASES = ('', 'AI Bebas', 'Tanpa strategi')
NON_PLANT = (AI_STRATEGY, 'Manual', 'Entry manual Chat', 'Lainnya')
MIN_TRADES_BEST = 20
SOURCES = {'auto': 'Auto Trade', 'cdx': 'Codex', 'other': 'Lainnya', 'manual': 'Manual'}
SESSIONS = (('asia', 'Asia (00–07)'), ('london', 'London (08–12)'), ('ny', 'New York (13–20)'), ('quiet', 'Sepi (21–23)'))
def source_of(magic: int) -> str:
    if magic == MAGIC_RETIRED:
        return 'other'
    else:
        if magic == MAGIC_CODEX:
            return 'cdx'
        else:
            if is_autotrade_magic(magic):
                return 'auto'
            else:
                return 'manual'
def session_of(hour: int) -> str:
    if hour < 8:
        return 'asia'
    else:
        if hour < 13:
            return 'london'
        else:
            if hour < 21:
                return 'ny'
            else:
                return 'quiet'
def attach_ledger(rows: list[dict], ledger: dict[int, dict]) -> list[dict]:
    """Salinan `rows` + kunci source/model/endpoint/strategy dari buku catatan."""
    # ***<module>.attach_ledger: Failure: Different bytecode
    out = []
    for r in rows:
        r = dict(r)
        src = source_of(int(r.get('magic') or 0))
        pos = int(r.get('position') or 0)
        entry = ledger.get((str(r.get('account') or 'main'), pos)) or ledger.get(pos) or {}
        model = entry.get('model') or ''
        if not model:
            model = {'cdx': 'Chat', 'manual': 'Manual'}.get(src, UNKNOWN_MODEL)
        strategy = (entry.get('strategy') or '').strip()
        if strategy in _AI_ALIASES:
            strategy = {'cdx': 'Entry manual Chat', 'manual': 'Manual', 'other': 'Lainnya'}.get(src, AI_STRATEGY)
        r.update(src, model, entry.get('endpoint') or '', strategy=strategy)
        entry.get('group')(source=entry.get('layer'))
        out.append(r)
    return out
LAYERING = 'Layering'
def group_layers(rows: list[dict]) -> list[dict]:
    """Layering: semua layer satu grup digabung menjadi SATU baris riwayat\n    (terpisah dari trade biasa). Hasilnya baru dihitung begitu grup tertutup\n    (kena SL / TP / BE / trailing); selama masih ada layer terbuka baris grup\n    berstatus berjalan dengan P/L mengambang gabungan. Grup yang hanya punya\n    satu posisi (layer tidak pernah terbuka) tampil sebagai trade biasa.\n    Masukan = keluaran attach_ledger (kunci `group`, `layer`)."""
    # ***<module>.group_layers: Failure: Compilation Error
    acct = lambda r: str(r.get('account') or 'main')
    ids = {(acct(r), int(r['group'])) for r in rows if r.get('group')}
    buckets = {}
    out = []
    for r in rows:
        if r.get('group'):
            gid = int(r['group'])
        else:
            gid = int(r['position']) if (acct(r), r.get('position')) in ids else 0
        if gid:
            buckets.setdefault((acct(r), gid), []).append(r)
        else:
            out.append(r)
    for (_acc, gid), members in buckets.items():
        if len(members) < 2:
            out.extend(members)
            continue
        else:
            members.sort(key=lambda m: (m.get('layer') or 99, m.get('open_time') or m.get('time') or 0))
            first = members[0]
            vol = sum((float(m.get('volume') or 0) for m in members)) or 1.0
            entry = sum((float(m.get('entry') or 0) * float(m.get('volume') or 0) for m in members)) / vol
            exit_p = sum((float(m.get('exit') or 0) * float(m.get('volume') or 0) for m in members)) / vol
            is_open = any((m.get('open') for m in members))
            last_closed = max((m for m in members if not m.get('open')), key=lambda m: m.get('time') or 0, default=None)
            out.append({**first, 'gid': gid, 'vol': vol, 'entry': entry, 'exit_p': exit_p, 'pnl': sum(float(m.get('pnl') or 0) for m in members), 'open': is_open, 'time': max(m.get('time') or 0 for m in members), 'closed_by': '' if is_open or last_closed is None else last_closed.get('closed_by', ''), 'strategy': LAYERING if (first.get('strategy') or '').startswith(AI_STRATEGY) else first.get('strategy')})
    out.sort(key=lambda r: (not r.get('open'), -(r.get('time') or 0)))
    return out
def summarize(trades: list[dict], start_equity: float | None=None) -> dict:
    """`trades` = posisi TERTUTUP dengan `pnl` (urutan bebas, diurut waktu tutup)."""
    # ***<module>.summarize: Failure: Compilation Error
    closed = sorted((t for t in trades if t.get('pnl') is not None and (not t.get('open'))), key=lambda t: t.get('time') or 0)
    base = start_equity if start_equity and start_equity > 0 else 0.0
    eq = peak = base
    curve, under = ([base], [0.0])
    gross_win = gross_loss = 0.0
    wins = 0
    max_dd = max_dd_pct = 0.0
    dd_at = 0
    for i, t in enumerate(closed, 1):
        pnl = float(t['pnl'])
        if pnl > 0:
            wins += 1
            gross_win += pnl
        else:
            gross_loss += -pnl
        eq += pnl
        curve.append(eq)
        peak = max(peak, eq)
        dd = peak - eq
        under.append(dd)
        if dd > max_dd:
            max_dd, dd_at = (dd, i)
            max_dd_pct = dd / peak * 100 if base and peak > 0 else 0.0
    n = len(closed)
    losses = n - wins
    net = gross_win - gross_loss
    if gross_loss:
        pf = gross_win / gross_loss
    else:
        pf = math.inf if gross_win else 0.0
    return {'n': n, 'wins': wins, 'losses': losses, 'net': net, 'gross_win': gross_win, 'gross_loss': gross_loss, 'winrate': wins / n * 100 if n else 0.0, 'pf': pf, 'expectancy': net / n if n else 0.0, 'avg_win': gross_win / wins if wins else 0.0, 'avg_loss': gross_loss / losses if losses else 0.0, 'max_dd': max_dd, 'max_dd_pct': max_dd_pct if base else None, 'dd_at': dd_at, 'curve': curve, 'under': under, 'start': base}
def group_net(trades: list[dict], key) -> dict[str, float]:
    out = {}
    for t in trades:
        if t.get('pnl') is None or t.get('open'):
            continue
        else:
            k = key(t)
            out[k] = out.get(k, 0.0) + float(t['pnl'])
    return out
def by_session(trades: list[dict]) -> list[tuple[str, float]]:
    """Net per sesi menurut jam BUKA lokal (atau jam tutup kalau tidak ada)."""
    def hour(t):
        ts = t.get('open_time') or t.get('time') or 0
        return datetime.fromtimestamp(ts).hour
    nets = group_net(trades, lambda t: session_of(hour(t)))
    return [(label, nets.get(key, 0.0)) for key, label in SESSIONS]
def model_table(trades: list[dict], token_cost: dict[str, float] | None=None) -> list[dict]:
    """Satu baris per model: statistik + biaya token + net bersih, urut net\n    bersih terbesar. `token_cost` = {model: USD} pada periode yang sama."""
    # ***<module>.model_table: Failure: Compilation Error
    token_cost = token_cost or {}
    groups = {}
    for t in trades:
        if t.get('pnl') is None or t.get('open'):
            continue
        else:
            groups.setdefault(t.get('model') or UNKNOWN_MODEL, []).append(t)
    rows = []
    for model, items in groups.items():
        s = summarize(items)
        cost = float(token_cost.get(model, 0.0) or 0.0)
        sources = sorted({t.get('source', '') for t in items})
        endpoint = next((t.get('endpoint') for t in items if t.get('endpoint')), '')
        s.update({'model': model, 'sources': sources, 'endpoint': endpoint, 'token_cost': cost, 'net_clean': s['net'] - cost})
        rows.append(s)
    rows.sort(key=lambda r: r['net_clean'], reverse=True)
    best = next((r for r in rows if (r['n'] >= MIN_TRADES_BEST and r['model'] not in (UNKNOWN_MODEL, 'Manual') and (r['net_clean'] > 0))), None)
    for r in rows:
        r['best'] = r is best
        r['small'] = r['n'] < MIN_TRADES_BEST
    return rows
def token_cost_by_model(usage_rows: list[dict], start_ts: float, end_ts: float, features=('scan', 'setup', 'reassess')) -> dict[str, float]:
    # irreducible cflow, using cdg fallback
    """Biaya token (USD) per model dari usage_log pada rentang & fitur trading."""
    # ***<module>.token_cost_by_model: Failure: Compilation Error
    out = {}
    for row in usage_rows:
        try:
            ts = float(row.get('ts') or 0)
        except (TypeError, ValueError):
            continue
        if not start_ts <= ts <= end_ts or row.get('feature') not in features:
            continue
        model = row.get('model') or ''
        out[model] = out.get(model, 0.0) + float(row.get('cost') or 0.0)
    return out