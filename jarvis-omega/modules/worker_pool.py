import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

# Правильные относительные импорты без префикса jarvis_omega
from modules.plugins.advego_job_hunter import AdvegoJobHunter

logger = logging.getLogger("jarvis.modules.worker_pool")

LEDGER_PATH = Path(__file__).parent.parent / "financial_ledger.json"
LEDGER_LOCK = asyncio.Lock()

class TaskType(str, Enum):
    LLM_CHAT = "llm_chat"
    HUNT_JOBS = "hunt_jobs"
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
        self._queue: asyncio.Queue = asyncio.Queue()  # Убрали жесткую типизацию для гибкости API
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
        logger.info(f"[Workers] Pool started with {self._num_workers} workers.")

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
        """ Автономный цикл планировщика """
        await asyncio.sleep(15)
        while not self._shutdown:
            try:
                # Постановка задачи на Advego раз в 30 минут
                await self.add_task(
                    prompt="Сканирование ленты Advego на наличие доступных заказов.",
                    task_type=TaskType.HUNT_JOBS
                )
                await asyncio.sleep(1800)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Scheduler] Error in autonomous cycle: {e}")
                await asyncio.sleep(60)

    async def _worker_loop(self, worker_id: int) -> None:
        while not self._shutdown:
            try:
                await self._running_event.wait()
                try:
                    raw_task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # --- Валидация и нормализация задачи из очереди ---
                task = None
                if isinstance(raw_task, Task):
                    task = raw_task
                elif isinstance(raw_task, dict):
                    try:
                        # Если прилетел dict из API — безопасно собираем из него объект Task
                        t_type = raw_task.get("task_type", TaskType.LLM_CHAT)
                        if isinstance(t_type, str):
                            try:
                                t_type = TaskType(t_type)
                            except ValueError:
                                t_type = TaskType.LLM_CHAT

                        task = Task(
                            prompt=raw_task.get("prompt", ""),
                            task_type=t_type,
                            metadata=raw_task.get("metadata", {})
                        )
                    except Exception as ex:
                        logger.error(f"Worker-{worker_id} failed to parse task dict: {ex}")
                
                if task:
                    await self._process_task(worker_id, task)
                else:
                    logger.error(f"Worker-{worker_id} received invalid task type: {type(raw_task)}")

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

            # Извлекаем строковое значение для логов и условий
            current_type = task.task_type.value if isinstance(task.task_type, TaskType) else str(task.task_type)

            if current_type == TaskType.LLM_CHAT.value:
                messages = [{"role": "user", "content": task.prompt}]
                response = await self._router.complete(messages)
                action_details = "Чат с пользователем"

            elif current_type == TaskType.HUNT_JOBS.value:
                hunter = AdvegoJobHunter(router=self._router)
                response, rev_rub = await hunter.hunt_and_execute()
                revenue_usd = rev_rub / 91.0
                action_details = "Работа на Advego"

            elapsed = round(time.time() - start, 3)
            cost_usd = self._estimate_cost(task.prompt, response)

            await self._write_ledger(
                worker_id=worker_id,
                task_type=current_type,
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
            logger.error(f"Task execution failed inside _process_task: {e}", exc_info=True)

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
        tokens = (len(prompt) + len(response)) / 4
        return (tokens / 1000) * 0.015
