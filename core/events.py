from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional
import json
import time
import uuid


@dataclass(frozen=True)
class TradeEvent:
    kind: str
    symbol: str = ""
    correlation_id: str = ""
    payload: Dict[str, Any] = None
    created_at: float = 0.0

    def __post_init__(self):
        if not self.correlation_id:
            object.__setattr__(self, "correlation_id", uuid.uuid4().hex)
        if self.payload is None:
            object.__setattr__(self, "payload", {})
        if not self.created_at:
            object.__setattr__(self, "created_at", time.time())

    def json(self) -> str:
        return json.dumps(asdict(self), default=str, sort_keys=True)
