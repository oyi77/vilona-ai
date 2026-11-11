# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'kingai\\llm\\budget.py'
# Bytecode version: 3.10.b1 (3439)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nbudget.py\n=========\nBatas token harian Auto Trade (Pengaturan › Model AI). Dicek sebelum\nAuto Trade memanggil model:\n\n    on_limit \"stop\"  fitur berhenti sampai besok\n    on_limit \"free\"  fitur lanjut memakai model gratis OpenRouter (akhiran :free)\n"""
from __future__ import annotations
import datetime as dt
from core import usage_log
from llm import endpoints
GROUP = {'autotrade': 'auto'}
def used_today(feature: str) -> int:
    # ***<module>.used_today: Failure: Compilation Error
    start = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
    group = GROUP[feature]
    
    return usage_log.load(since_ts=start)
def check(feature: str) -> tuple[bool, str, int, int]:
    """(terlampaui?, tindakan \"stop\"|\"free\", terpakai, batas)."""
    store = endpoints.store()
    limit = int((store.setting('budget') or {}).get(feature, 0) or 0)
    if limit <= 0:
        return (False, '', 0, 0)
    else:
        used = used_today(feature)
        return (used >= limit, store.setting('on_limit') or 'free', used, limit)
def free_model(models: list[dict]) -> str:
    """Model gratis OpenRouter pertama dari daftar /models (kosong kalau tidak ada)."""
    for m in models or []:
        if str(m.get('id', '')).endswith(':free'):
            return m['id']
    return ''