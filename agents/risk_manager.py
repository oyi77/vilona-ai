from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Union, Any
from types import SimpleNamespace
from agents import Signal, MarketSnapshot
from config import TradingConfig, get_config

@dataclass
class RiskVerdict:
    approved: bool
    lot_size: float = 0.0
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    rr_ratio: float = 0.0
    reason: str = ""

def evaluate(
    signal: Signal,
    snapshot: MarketSnapshot,
    equity_usd: float,
    cfg: Optional[Union[TradingConfig, dict[str, Any]]] = None,
    daily_pl_usd: float = 0.0,
    open_positions_count: int = 0,
    config: Optional[dict[str, Any]] = None,
) -> RiskVerdict:
    effective_cfg = config if config is not None else cfg
    if effective_cfg is None:
        effective_cfg = get_config().trading
    elif isinstance(effective_cfg, dict):
        effective_cfg = SimpleNamespace(**effective_cfg)
    cfg = effective_cfg
    if signal.action == "WAIT":
        return RiskVerdict(False, reason="signal=WAIT")
    if signal.confidence < cfg.min_confidence:
        return RiskVerdict(False, reason=f"confidence {signal.confidence:.2f}<{cfg.min_confidence}")
    if snapshot.spread_pct > max(cfg.max_spread_pct_default, cfg.max_spread_pct):
        return RiskVerdict(False, reason=f"spread {snapshot.spread_pct:.3f}% too wide")
    if open_positions_count >= cfg.max_concurrent_positions:
        return RiskVerdict(False, reason="max concurrent positions reached")
    if daily_pl_usd <= -(equity_usd * cfg.max_daily_loss_pct / 100.0):
        return RiskVerdict(False, reason="daily loss limit hit")
    entry = signal.entry_hint or (snapshot.tick_ask if signal.action == "BUY" else snapshot.tick_bid)
    atr = snapshot.atr_15m or (entry * 0.005)
    sl_dist = cfg.sl_atr_mult * atr
    tp_dist = cfg.tp_atr_mult * atr
    if signal.action == "BUY":
        sl_price = entry - sl_dist
        tp_price = entry + tp_dist
    else:
        sl_price = entry + sl_dist
        tp_price = entry - tp_dist
    risk_usd = equity_usd * (cfg.max_risk_per_trade_pct / 100.0)
    per_unit_risk = abs(entry - sl_price)
    if per_unit_risk <= 0:
        return RiskVerdict(False, reason="zero SL distance")
    lot = risk_usd / per_unit_risk
    lot = max(0.0, round(lot, 6))
    if lot <= 0:
        return RiskVerdict(False, reason="computed lot=0")

    rr = tp_dist / sl_dist if sl_dist else 0.0
    return RiskVerdict(
        approved=True,
        lot_size=lot,
        sl_price=round(sl_price, 8),
        tp_price=round(tp_price, 8),
        rr_ratio=round(rr, 2),
        reason=f"approved conf={signal.confidence:.2f} lot={lot:.4f} rr={rr:.2f}",
    )
