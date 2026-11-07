from __future__ import annotations
import json
from typing import Optional
from agents import Signal
from agents.risk_manager import RiskVerdict

SYSTEM_PROMPT = (
    "You are an independent judge reviewing a proposed trade. Look for "
    "logical flaws, overfitting to recent noise, or ignored risks. "
    "Return JSON only: {\"verdict\": \"APPROVE|VETO\", \"reason\": \"...\"}"
)

def build_user_prompt(signal: Signal, risk: RiskVerdict, research: Optional[dict] = None) -> str:
    return json.dumps({
        "signal": {
            "symbol": signal.symbol,
            "action": signal.action,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "entry_hint": signal.entry_hint,
            "sl_hint": signal.sl_hint,
            "tp_hint": signal.tp_hint,
        },
        "risk_verdict": {
            "approved": risk.approved,
            "lot_size": risk.lot_size,
            "sl_price": risk.sl_price,
            "tp_price": risk.tp_price,
            "rr_ratio": risk.rr_ratio,
            "reason": risk.reason,
        },
        "research": research or {},
    }, default=str)

def parse_judge(raw: str) -> tuple[bool, str]:
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
    verdict = str(data.get("verdict", "APPROVE")).upper()
    reason = str(data.get("reason", ""))[:500]
    return (verdict != "VETO", reason)
