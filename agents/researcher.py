from __future__ import annotations
import json
from typing import Optional
from agents import MarketSnapshot

SYSTEM_PROMPT = (
    "You are a market researcher. Summarise trend structure, key levels, "
    "and any catalysts from the supplied snapshot. Do NOT give trade advice. "
    "Return JSON only: {\"trend\": \"up|down|range\", \"key_levels\": [...], "
    "\"catalysts\": [...], \"summary\": \"...\"}"
)

def build_user_prompt(snapshot: MarketSnapshot) -> str:
    payload = {
        "symbol": snapshot.symbol,
        "bid": snapshot.tick_bid,
        "ask": snapshot.tick_ask,
        "spread_pct": snapshot.spread_pct,
        "atr_15m": snapshot.atr_15m,
        "candles_15m_tail": snapshot.candles_15m[-20:],
        "candles_1h_tail": snapshot.candles_1h[-20:],
        "news": snapshot.news_headlines[:10],
    }
    return json.dumps(payload, default=str)

def parse_research(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {"trend": "unknown", "key_levels": [], "catalysts": [], "summary": raw[:500]}
