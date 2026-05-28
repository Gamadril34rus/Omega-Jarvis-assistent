import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

# Импорты плагинов (путь должен соответствовать структуре jarvis-omega/modules/plugins/)
from modules.plugins.advego_job_hunter import AdvegoJobHunter

logger = logging.getLogger("jarvis.modules.worker_pool")

LEDGER_PATH = Path(__file__).parent.parent / "financial_ledger.json"
LEDGER_LOCK = asyncio.Lock()

class TaskType(str, Enum):
    LLM_CHAT = "llm_chat"
    HUNT_JOBS = "hunt_jobs"        # Поиск заказов на Advego
    POST_CONTENT = "post_content"
    SCALE_INFRA = "scale_infra"

@dataclass
class Task:
    prompt: str
    task_type: TaskType = TaskType.LLM_CHAT
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

class WorkerPool:
    def __init__(self, router, brain, notifier=None, num_workers: int = 3):
        self._router = router
        self._brain = brain
        self._notifier = notifier
        self._num_workers = num_workers
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._running_event = asyncio.Event()
        self._running_event.set()
        self._worker_tasks: list[asyncio.Task] = []
        self._shutdown = False

    async def start(self) -> None:
        self._shutdown = False
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(i), name=f"worker-{i}")
            for i in range(self._num_workers)
        ]
        asyncio.create_task(self._autonomous_scheduler())
        logger.info(f"[Workers] Pool started with {self._num_workers} workers + Advego Autonomy.")

    async def stop(self) -> None:
        self._shutdown = True
        self._running_event.set()
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)

    async def add_task(self, prompt: str, task_type: TaskType = TaskType.LLM_CHAT, metadata: dict | None = None) -> None:
        task = Task(prompt=prompt, task_type=task_type, metadata=metadata or {})
        await self._queue.put(task)

    async def _autonomous_scheduler(self):
        """ Цикл Jarvis для автоматического поиска прибыли """
        await asyncio.sleep(10) 
        while not self._shutdown:
            try:
                # Ставим задачу HUNT_JOBS раз в 30 минут
                await self.add_task(
                    prompt="Сканирование ленты Advego на наличие заказов без тендера.",
                    task_type=TaskType.HUNT_JOBS
                )
                await asyncio.sleep(1800) 
            except Exception as e:
                logger.error(f"[Scheduler] Error: {e}")
                await asyncio.sleep(60)

    async def _worker_loop(self, worker_id: int) -> None:
        while not self._shutdown:
            try:
                await self._running_event.wait()
                try:
                    task: Task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                await self._process_task(worker_id, task)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Worker-{worker_id} error: {e}")

    async def _process_task(self, worker_id: int, task: Task) -> None:
        start = time.time()
        
        try:
            revenue_usd = 0.0
            response = ""
            action_details = ""

            if task.task_type == TaskType.LLM_CHAT:
                messages = [{"role": "user", "content": task.prompt}]
                response = await self._router.complete(messages)
                action_details = "Чат с пользователем"

            elif task.task_type == TaskType.HUNT_JOBS:
                # Включаем наш Advego Hunter
                hunter = AdvegoJobHunter(router=self._router)
                response, rev_rub = await hunter.hunt_and_execute()
                revenue_usd = rev_rub / 91.0 # Конвертация рубля в USD для леджера
                action_details = "Охота на Advego"

            elapsed = round(time.time() - start, 3)
            cost_usd = self._estimate_cost(task.prompt, response)

            await self._write_ledger(
                worker_id=worker_id,
                task_type=task.task_type.value,
                prompt=task.prompt,
                response=response,
                cost_usd=cost_usd,
                revenue_usd=revenue_usd,
                elapsed=elapsed,
                metadata=task.metadata
            )

            if self._notifier and revenue_usd > 0:
                await self._notifier.send_alert(
                    f"💰 <b>Jarvis заработал деньги!</b>\n"
                    f"Действие: <code>{action_details}</code>\n"
                    f"Результат: {response}\n"
                    f"Профит: <code>${revenue_usd:.2f}</code>",
                    dedup_key="revenue_alert"
                )

        except Exception as e:
            logger.error(f"Task failed: {e}")

    async def _write_ledger(self, **kwargs) -> None:
        async with LEDGER_LOCK:
            try:
                if LEDGER_PATH.exists():
                    data = json.loads(LEDGER_PATH.read_text())
                else:
                    data = {"total_revenue_usd": 0.0, "total_expenses_usd": 0.0, "transactions": []}

                data["total_revenue_usd"] += kwargs.get("revenue_usd", 0.0)
                data["total_expenses_usd"] += kwargs.get("cost_usd", 0.0)
                data["transactions"].append({
                    "ts": time.time(),
                    "type": kwargs.get("task_type"),
                    "rev": kwargs.get("revenue_usd"),
                    "cost": kwargs.get("cost_usd")
                })
                LEDGER_PATH.write_text(json.dumps(data, indent=2))
            except Exception as e:
                logger.error(f"Ledger error: {e}")

    @staticmethod
    def _estimate_cost(prompt: str, response: str) -> float:
        # Примерная оценка стоимости токенов ИИ
        tokens = (len(prompt) + len(response)) / 4
        return (tokens / 1000) * 0.01
