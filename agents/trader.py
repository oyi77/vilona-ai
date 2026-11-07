from __future__ import annotations
import json
from typing import Optional
from agents import Signal, MarketSnapshot

SYSTEM_PROMPT = (
    "You are a disciplined technical trader. Given a market snapshot and "
    "optional research brief, decide ONE action: BUY, SELL, or WAIT. "
    "Bias toward WAIT when evidence is thin. Return JSON only: "
    "{\"action\": \"BUY|SELL|WAIT\", \"confidence\": 0.0-1.0, \"reason\": \"...\", "
    "\"entry_hint\": number|null, \"sl_hint\": number|null, \"tp_hint\": number|null}"
)

def build_user_prompt(snapshot: MarketSnapshot, research: Optional[dict] = None) -> str:
    payload = {
        "snapshot": {
            "symbol": snapshot.symbol,
            "bid": snapshot.tick_bid,
            "ask": snapshot.tick_ask,
            "spread_pct": snapshot.spread_pct,
            "atr_15m": snapshot.atr_15m,
            "candles_15m_tail": snapshot.candles_15m[-40:],
            "candles_1h_tail": snapshot.candles_1h[-40:],
        },
        "research": research or {},
    }
    return json.dumps(payload, default=str)

def parse_signal(raw: str, symbol: str) -> Signal:
    data = {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        s = raw.find("{"); e = raw.rfind("}")
        if s >= 0 and e > s:
            try:
                data = json.loads(raw[s:e + 1])
            except json.JSONDecodeError:
                data = {}
    action = str(data.get("action", "WAIT")).upper()
    if action not in ("BUY", "SELL", "WAIT"):
        action = "WAIT"
    return Signal(
        symbol=symbol,
        action=action,
        confidence=float(data.get("confidence", 0.0)),
        reason=str(data.get("reason", ""))[:500],
        entry_hint=data.get("entry_hint"),
        sl_hint=data.get("sl_hint"),
        tp_hint=data.get("tp_hint"),
        source_role="trader",
    )
