from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import time


@dataclass
class HealthSnapshot:
    state: str = "stopped"
    bridge_connected: bool = False
    database_healthy: bool = True
    llm_healthy: Optional[bool] = None
    last_scan_at: Optional[float] = None
    last_success_at: Optional[float] = None
    last_error: str = ""
    error_count: int = 0
    active_symbols: int = 0
    paper: bool = True

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.last_scan_at:
            data["last_scan_age_seconds"] = round(time.time() - self.last_scan_at, 2)
        return data
