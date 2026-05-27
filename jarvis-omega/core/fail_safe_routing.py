import asyncio
import logging
import os
import random
from enum import Enum

import httpx

logger = logging.getLogger("jarvis.router")


class Provider(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"
    SILICONFLOW = "siliconflow"
    OPENROUTER = "openrouter"


CASCADE_ORDER = [
    Provider.GROQ,
    Provider.GEMINI,
    Provider.DEEPSEEK,
    Provider.ZHIPU,
    Provider.SILICONFLOW,
    Provider.OPENROUTER,
]

JITTER_MIN_SEC = 15
JITTER_MAX_SEC = 45


class ProviderConfig:
    def __init__(self):
        self.configs = {
            Provider.GROQ: {
                "api_key": os.getenv("GROQ_API_KEY", ""),
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b-versatile",
            },
            Provider.GEMINI: {
                "api_key": os.getenv("GEMINI_API_KEY", ""),
                "base_url": "https://generativelanguage.googleapis.com/v1",
                # Системное имя для Google API (строчные буквы, дефисы)
                "model": "gemini-2.5-flash-lite",
            },
            Provider.DEEPSEEK: {
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-chat",
            },
            Provider.ZHIPU: {
                "api_key": os.getenv("ZHIPU_API_KEY", ""),
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                # Системное имя для Zhipu
                "model": "glm-4.7-flash",
            },
            Provider.SILICONFLOW: {
                "api_key": os.getenv("SILICONFLOW_API_KEY", ""),
                "base_url": "https://api.siliconflow.cn/v1",
                # В SiliconFlow часто требуется указывать вендора. 
                # Если будет выдавать ошибку 404, замени на "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
                "model": "DeepSeek-R1-Qwen-7B",
            },
            Provider.OPENROUTER: {
                "api_key": os.getenv("OPENROUTER_API_KEY", ""),
                "base_url": "https://openrouter.ai/api/v1",
                "model": "meta-llama/llama-3.1-8b-instruct:free",
            },
        }

    def get(self, provider: Provider) -> dict:
        return self.configs[provider]


class FailSafeRouter:
    def __init__(self, brain=None, notifier=None):
        self._config = ProviderConfig()
        self._current_provider_index = 0
        self._brain = brain
        self._notifier = notifier

    @property
    def current_provider(self) -> Provider:
        return CASCADE_ORDER[self._current_provider_index]

    async def complete(self, messages: list[dict], **kwargs) -> str:
        for _ in range(len(CASCADE_ORDER)):
            provider = CASCADE_ORDER[self._current_provider_index]
            try:
                result = await self._call_provider(provider, messages, **kwargs)
                if self._brain:
                    await self._brain.update_provider(provider.value)
                    await self._brain.record_request(success=True)
                return result
            except RateLimitError as e:
                delay = self._exponential_backoff_with_jitter(e.retry_after)
                logger.warning(
                    f"[Router] {provider.value} → HTTP 429. "
                    f"Backoff {delay:.1f}s before switching."
                )
                await asyncio.sleep(delay)
                await self._switch_provider(from_provider=provider)
            except ProviderError as e:
                logger.error(f"[Router] {provider.value} failed: {e}. Switching.")
                if self._brain:
                    await self._brain.record_request(success=False)
                await self._switch_provider(from_provider=provider)

        raise RuntimeError("All providers exhausted. No response available.")

    async def _call_provider(self, provider: Provider, messages: list[dict], **kwargs) -> str:
        cfg = self._config.get(provider)
        
        if not cfg["api_key"]:
            raise ProviderError(f"No API key configured for {provider.value}")

        if provider == Provider.GEMINI:
            return await self._call_gemini(cfg, messages, **kwargs)

        headers = {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        }
        if provider == Provider.OPENROUTER:
            headers["HTTP-Referer"] = "https://jarvis-omega.local"
            headers["X-Title"] = "Jarvis-Omega"

        payload = {"model": cfg["model"], "messages": messages, **kwargs}
        url = f"{cfg['base_url']}/chat/completions"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", 0))
            raise RateLimitError(retry_after=retry_after)
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        return resp.json()["choices"][0]["message"]["content"]

    async def _call_gemini(self, cfg: dict, messages: list[dict], **kwargs) -> str:
        prompt = "\n".join(m.get("content", "") for m in messages)
        url = (
            f"{cfg['base_url']}/models/{cfg['model']}:generateContent"
            f"?key={cfg['api_key']}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", 0))
            raise RateLimitError(retry_after=retry_after)
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    async def _switch_provider(self, from_provider: Provider | None = None) -> None:
        prev_name = (from_provider or CASCADE_ORDER[self._current_provider_index]).value
        self._current_provider_index = (self._current_provider_index + 1) % len(CASCADE_ORDER)
        next_provider = CASCADE_ORDER[self._current_provider_index]
        next_name = next_provider.value

        logger.info(f"[Router] Cascade switch: {prev_name} → {next_name}")

        if self._notifier:
            await self._notifier.send_alert(
                f"⚠️ <b>Alert: Переключение на резервный API</b>\n"
                f"<code>{prev_name}</code> недоступен → <code>{next_name}</code>",
                dedup_key=f"provider_switch:{next_name}",
            )

    def _exponential_backoff_with_jitter(self, retry_after: float, attempt: int = 1) -> float:
        base_delay = max(retry_after, 2 ** attempt)
        jitter = random.uniform(JITTER_MIN_SEC, JITTER_MAX_SEC)
        return base_delay + jitter


class RateLimitError(Exception):
    def __init__(self, retry_after: float = 0):
        self.retry_after = retry_after
        super().__init__(f"Rate limit hit, retry_after={retry_after}s")


class ProviderError(Exception):
    pass
