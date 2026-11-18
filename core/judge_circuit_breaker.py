"""Circuit breaker for LLM judge calls.

The judge endpoint took the full 30s timeout on every attempt, which stalled the
30s scan loop and made the paper soak produce no usable verdicts. The breaker
stops calling a failing judge, degrades to the deterministic R:R gate, and probes
again after a cooldown.

States:
- closed:    normal operation, calls allowed.
- open:      threshold of consecutive failures reached, calls blocked until the
             cooldown elapses.
- half_open: one probe call allowed; success closes the breaker, failure reopens it.
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("vilona-ai.judge_breaker")


class JudgeCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 120.0):
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._lock = threading.Lock()
        self.failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    def allow(self) -> bool:
        """Return True when a judge call may proceed."""
        with self._lock:
            if self._opened_at is None:
                return True
            if (time.monotonic() - self._opened_at) < self.cooldown_seconds:
                return False
            # Cooldown elapsed: permit a single probe.
            if self._half_open_probe_in_flight:
                return False
            self._half_open_probe_in_flight = True
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._opened_at is not None:
                logger.info("Judge circuit breaker closed after a successful probe")
            self.failure_count = 0
            self._opened_at = None
            self._half_open_probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            was_open = self._opened_at is not None
            self._half_open_probe_in_flight = False
            if was_open or self.failure_count >= self.failure_threshold:
                self._opened_at = time.monotonic()
                if not was_open:
                    logger.warning(
                        "Judge circuit breaker opened after %d consecutive failures; "
                        "degrading to the deterministic R:R gate for %.0fs",
                        self.failure_count, self.cooldown_seconds,
                    )

    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            if (time.monotonic() - self._opened_at) < self.cooldown_seconds:
                return "open"
            return "half_open"
