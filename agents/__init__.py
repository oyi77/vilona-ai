from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

ROLE_RESEARCHER = "researcher"
ROLE_TRADER = "trader"
ROLE_RISK_MANAGER = "risk_manager"
ROLE_JUDGE = "judge"
ALL_ROLES = (ROLE_RESEARCHER, ROLE_TRADER, ROLE_RISK_MANAGER, ROLE_JUDGE)
DEFAULT_ROLES = (ROLE_TRADER, ROLE_RISK_MANAGER)

@dataclass
class Signal:
    symbol: str
    action: str
    confidence: float = 0.0
    reason: str = ""
    entry_hint: Optional[float] = None
    sl_hint: Optional[float] = None
    tp_hint: Optional[float] = None
    source_role: str = ROLE_TRADER

@dataclass
class MarketSnapshot:
    symbol: str
    tick_bid: float
    tick_ask: float
    candles_15m: list
    candles_1h: list
    spread_pct: float
    atr_15m: float
    news_headlines: list

def roles_for(enabled: list[str]) -> tuple:
    if not enabled:
        return DEFAULT_ROLES
    picked = [r for r in ALL_ROLES if r in enabled]
    return tuple(picked) or DEFAULT_ROLES
