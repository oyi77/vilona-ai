"""SystemOne/JEV integration hook for Vilona AI v2."""
from __future__ import annotations
import json
import logging
import aiohttp
from typing import Optional, Dict, Any
from config import get_config

logger = logging.getLogger(__name__)

SYSTEMONE_ENDPOINT = "https://jev.ai/api/v1/hooks"


async def send_to_systemone(signal: Dict[str, Any]) -> bool:
    cfg = get_config()
    if not cfg.systemone_enabled or not cfg.systemone_endpoint:
        return False

    payload = {
        "type": "vilona_signal",
        "version": cfg.build.version,
        **signal,
    }

    try:
        headers = {
            "Authorization": f"Bearer {cfg.systemone_api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                cfg.systemone_endpoint or SYSTEMONE_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"SystemOne/JEV hook sent successfully: {payload.get('symbol')}")
                    return True
                logger.warning(f"SystemOne/JEV hook failed: {resp.status}")
                return False
    except Exception as e:
        logger.error(f"Failed to send to SystemOne/JEV: {e}")
        return False


async def fetch_systemone_signals(symbol: str) -> Optional[list]:
    cfg = get_config()
    if not cfg.systemone_enabled:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{cfg.systemone_endpoint}/signals/{symbol}",
                headers={"Authorization": f"Bearer {cfg.systemone_api_key}"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except:
        return None
