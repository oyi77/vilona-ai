"""Market-condition guards: weekend entry cutoff, weekend flatten, and stale-tick check.

All timing decisions are relative to a supplied server/tick timestamp, never
the host system clock. Standard Forex weekly hours (22:00 UTC Friday close,
21:00 UTC Sunday open) apply unless overridden by symbol session data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class MarketGuardDecision:
    allowed: bool
    reason: str


def evaluate_tick_freshness(*, tick_timestamp_s: float | None,
                            now_s: float | None,
                            max_age_s: float = 30.0) -> MarketGuardDecision:
    """Fail-closed freshness check; absent or non-finite timestamp halts entries."""
    if tick_timestamp_s is None or now_s is None:
        return MarketGuardDecision(False, "tick timestamp unavailable")
    try:
        t = float(tick_timestamp_s)
        n = float(now_s)
    except (TypeError, ValueError):
        return MarketGuardDecision(False, "invalid tick timestamp format")
    if not math.isfinite(t) or not math.isfinite(n):
        return MarketGuardDecision(False, "invalid non-finite tick timestamp")
    if t <= 0 or n <= 0 or max_age_s <= 0:
        return MarketGuardDecision(False, "invalid tick time parameters")
    age = n - t
    if age < -120.0:
        return MarketGuardDecision(False, f"tick timestamp is in the future ({abs(age):.1f}s ahead)")
    if age > max_age_s:
        return MarketGuardDecision(False, f"stale tick ({age:.1f}s > {max_age_s:.1f}s)")
    return MarketGuardDecision(True, "tick fresh")


def evaluate_weekend_guard(*, server_epoch_s: float | None,
                           entry_cutoff_min: int = 120,
                           open_grace_min: int = 30) -> MarketGuardDecision:
    """Fail-closed weekend entry filter using broker server epoch (standard 22:00 UTC Friday close)."""
    if server_epoch_s is None:
        return MarketGuardDecision(False, "server time unavailable for weekend check")
    try:
        dt = datetime.fromtimestamp(float(server_epoch_s), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return MarketGuardDecision(False, "invalid server time for weekend check")

    weekday = dt.weekday()  # Monday=0, Friday=4, Saturday=5, Sunday=6
    hour = dt.hour
    minute = dt.minute
    minute_of_day = hour * 60 + minute

    # Friday close is 22:00 UTC = 1320 minutes
    close_minute = 22 * 60
    cutoff_minute = close_minute - entry_cutoff_min

    # Friday after cutoff
    if weekday == 4 and minute_of_day >= cutoff_minute:
        return MarketGuardDecision(False, "weekend entry cutoff active (Friday pre-close)")

    # Saturday is entirely closed
    if weekday == 5:
        return MarketGuardDecision(False, "market closed (Saturday)")

    # Sunday before open (21:00 UTC) + open grace
    open_minute = 21 * 60
    if weekday == 6:
        if minute_of_day < open_minute:
            return MarketGuardDecision(False, "market closed (Sunday pre-open)")
        if minute_of_day < open_minute + open_grace_min:
            return MarketGuardDecision(False, "weekend open grace active (Sunday post-open)")

    return MarketGuardDecision(True, "market session open")


def is_weekend_flatten_window(*, server_epoch_s: float | None,
                              flatten_min: int = 60) -> bool:
    """True if server time is in the Friday flatten window (default: last 60m before 22:00 UTC close)."""
    if server_epoch_s is None:
        return False
    try:
        dt = datetime.fromtimestamp(float(server_epoch_s), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return False

    if dt.weekday() != 4:  # Friday only
        return False

    minute_of_day = dt.hour * 60 + dt.minute
    close_minute = 22 * 60
    flatten_start = close_minute - flatten_min
    return flatten_start <= minute_of_day < close_minute
