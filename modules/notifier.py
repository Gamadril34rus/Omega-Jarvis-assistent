import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("jarvis.notifier")

COOLDOWN_SEC = 300
MAX_HISTORY = 10


@dataclass
class AlertRecord:
    ts: float
    text: str
    dedup_key: str

    def formatted(self) -> str:
        dt = time.strftime("%H:%M:%S", time.localtime(self.ts))
        first_line = self.text.split("\n")[0]
        clean = first_line.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", "")
        return f"[{dt}] {clean}"

    def as_dict(self) -> dict:
        return {
            "ts": self.ts,
            "text": self.text,
            "dedup_key": self.dedup_key,
        }


class Notifier:
    """
    Sends Telegram messages to TELEGRAM_ADMIN_ID.
    Deduplicates by message key: same key won't fire again within COOLDOWN_SEC.
    Keeps an in-memory history of the last MAX_HISTORY sent alerts.
    """

    def __init__(self):
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._admin_id = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
        self._cache: dict[str, float] = {}
        self._history: list[AlertRecord] = []

    def _is_suppressed(self, key: str) -> bool:
        last = self._cache.get(key, 0.0)
        return (time.time() - last) < COOLDOWN_SEC

    def _mark_sent(self, key: str) -> None:
        self._cache[key] = time.time()

    def _record(self, text: str, key: str) -> None:
        self._history.append(AlertRecord(ts=time.time(), text=text, dedup_key=key))
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[-MAX_HISTORY:]

    def get_history(self) -> list[AlertRecord]:
        return list(reversed(self._history))

    def get_history_dicts(self) -> list[dict]:
        return [r.as_dict() for r in reversed(self._history)]

    async def send_alert(self, text: str, dedup_key: str | None = None) -> None:
        if not self._token or not self._admin_id:
            logger.warning("[Notifier] Token or admin_id not configured. Alert skipped.")
            return

        key = dedup_key or text[:120]

        if self._is_suppressed(key):
            logger.debug(f"[Notifier] Suppressed (cooldown active): {key!r}")
            return

        self._mark_sent(key)
        self._record(text, key)

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._admin_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info(f"[Notifier] Alert sent: {key!r}")
            else:
                logger.warning(
                    f"[Notifier] Telegram API returned {resp.status_code}: {resp.text[:100]}"
                )
        except Exception as e:
            logger.error(f"[Notifier] Failed to send alert: {e}")
