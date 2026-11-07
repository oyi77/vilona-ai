"""Sigma version of Vilona AI v2 — Telegram auth, persistence layer, LLM signal generation, 
multi-agent orchestration, headless/VPS support, and safety-first paper trading default.
"""
from __future__ import annotations
import asyncio
import time
from pathlib import Path

from config import get_config
from trading.bridge_ccxt import CCXTBridge


def main():
    cfg = get_config()
    try:
        bridge = CCXTBridge(cfg.exchange)
        if not bridge.connect():
            return 1
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
