import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.brain")

LEDGER_PATH = Path(__file__).parent.parent / "financial_ledger.json"


@dataclass
class SystemMetrics:
    uptime_seconds: float = 0.0
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    active_provider: str = "unknown"
    provider_switches: int = 0
    workers_paused: bool = False
    profit_usd: float = 0.0
    last_updated: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        if self.requests_total == 0:
            return 0.0
        return round(self.requests_success / self.requests_total * 100, 2)


class Brain:
    def __init__(self):
        self._metrics = SystemMetrics()
        self._start_time = time.time()
        self._lock = asyncio.Lock()

    async def update_provider(self, provider: str) -> None:
        async with self._lock:
            if self._metrics.active_provider != provider:
                self._metrics.provider_switches += 1
                self._metrics.active_provider = provider
                logger.info(f"[Brain] Active provider set to: {provider}")

    async def record_request(self, success: bool) -> None:
        async with self._lock:
            self._metrics.requests_total += 1
            if success:
                self._metrics.requests_success += 1
            else:
                self._metrics.requests_failed += 1
            self._metrics.last_updated = time.time()

    async def pause_workers(self) -> None:
        async with self._lock:
            self._metrics.workers_paused = True
            logger.info("[Brain] Workers paused.")

    async def resume_workers(self) -> None:
        async with self._lock:
            self._metrics.workers_paused = False
            logger.info("[Brain] Workers resumed.")

    async def get_metrics(self) -> dict:
        async with self._lock:
            self._metrics.uptime_seconds = round(time.time() - self._start_time, 1)
            self._metrics.profit_usd = self._read_ledger_profit()
            return asdict(self._metrics) | {"success_rate": self._metrics.success_rate}

    def _read_ledger_profit(self) -> float:
        try:
            if LEDGER_PATH.exists():
                data = json.loads(LEDGER_PATH.read_text())
                return float(data.get("total_profit_usd", 0.0))
        except Exception:
            pass
        return 0.0


brain = Brain()
