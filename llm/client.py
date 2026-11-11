from __future__ import annotations
import asyncio
import json
import logging
from typing import Optional, Dict, Any
import aiohttp

from config import get_config, LLMConfig

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.config = get_config().llm
        self._session = None
        self._base_url = self.config.base_url or {
            'openrouter': 'https://openrouter.ai/api/v1',
            'anthropic': 'https://api.anthropic.com',
            'openai': 'https://api.openai.com/v1',
        }.get(self.config.provider, 'https://api.openai.com/v1')

    async def _chat(self, system_prompt: str, user_prompt: str, model: str,
                    temperature: float, max_tokens: int) -> Optional[Dict[str, Any]]:
        """OpenAI-compatible chat with SSE streaming fallback.

        Some gateways (combo routers) only deliver non-streaming responses
        after all upstreams settle; SSE returns first-token fast and lets us
        assemble the full text incrementally. Usage from the final chunk is
        recorded to core/usage_log.py (KingAI parity).
        """
        from core import usage_log
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self.config.api_key}",
                   "Content-Type": "application/json"}
        payload = {"model": model, "temperature": temperature,
                   "max_tokens": max_tokens, "stream": True,
                   "messages": [{"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}]}
        text_parts: list = []
        usage = None
        try:
            async with session.post(f"{self._base_url}/chat/completions",
                                    json=payload, headers=headers) as resp:
                if resp.status != 200:
                    logger.error("LLM API error %s: %s", resp.status,
                                 (await resp.text())[:300])
                    return None
                async for raw in resp.content:
                    line = raw.decode('utf-8', errors='replace').strip()
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if data == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if chunk.get('usage'):
                        usage = chunk['usage']
                    for choice in chunk.get('choices') or []:
                        delta = choice.get('delta') or {}
                        piece = delta.get('content')
                        if piece:
                            text_parts.append(piece)
        except asyncio.TimeoutError:
            logger.error("LLM stream timeout after %ss", self.config.timeout)
            return None
        except Exception as e:
            logger.error("LLM stream failed: %s", e)
            return None
        if usage:
            usage_log.record(
                feature='scan', model=model,
                prompt=int(usage.get('prompt_tokens', 0) or 0),
                completion=int(usage.get('completion_tokens', 0) or 0),
                pricing=None, endpoint=str(self._base_url), cost=None,
            )
        return {"text": ''.join(text_parts), "usage": usage}

    async def _get_session(self):
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _request(self, url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            session = await self._get_session()
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            
            if self.config.provider == 'anthropic':
                headers['x-api-key'] = self.config.api_key
                headers.pop('Authorization')
                payload['model'] = self.config.model
                payload['max_tokens'] = self.config.max_tokens
                payload['temperature'] = self.config.temperature
            elif self.config.provider == 'openrouter':
                headers['HTTP-Referer'] = 'https://vilona-v2.dev'
                headers['X-Title'] = 'Vilona AI v2'
                payload['model'] = self.config.model
                payload['max_tokens'] = self.config.max_tokens
                payload['temperature'] = self.config.temperature
            else:
                payload['model'] = self.config.model
                payload['max_tokens'] = self.config.max_tokens
                payload['temperature'] = self.config.temperature

            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"LLM API error {resp.status}: {await resp.text()}")
                    return None
                return await resp.json()
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            return None

    async def generate_signal(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """
        Generate a trading signal from LLM.
        Returns raw response text.
        """
        model = model or self.config.model
        temperature = temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens
        # OpenAI-compatible gateways (incl. combo routers): SSE stream.
        if self.config.provider != 'anthropic':
            result = await self._chat(system_prompt, user_prompt, model,
                                      temperature, max_tokens)
            if not result:
                return None
            content = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return content or result.get("text") or None
        # Native Anthropic Messages API path.
        url = f'{self._base_url}/v1/messages'
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_prompt}],
            "system": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        result = await self._request(url, payload)
        if not result:
            return None
        return result.get('content', [{}])[0].get('text', '')

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
