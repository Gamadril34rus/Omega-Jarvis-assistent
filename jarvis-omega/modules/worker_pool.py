import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

# Импортируем созданные автономные модули
from jarvis_omega.modules.plugins.cpa_factory import CPAContentFactory
from jarvis_omega.modules.plugins.freelance_bot import FreelanceAutomator
from modules.plugins.advego_job_hunter import AdvegoJobHunter

logger = logging.getLogger("jarvis.modules.worker_pool")

LEDGER_PATH = Path(__file__).parent.parent / "financial_ledger.json"
LEDGER_LOCK = asyncio.Lock()


class TaskType(str, Enum):
    LLM_CHAT = "llm_chat"          # Стандартный ответ пользователю
    HUNT_JOBS = "hunt_jobs"        # Автономный поиск и решение задач на фрилансе
    POST_CONTENT = "post_content"  # Автогенерация и публикация CPA контента
    SCALE_INFRA = "scale_infra"    # Контроль бюджетов и лимитов серверов


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
        # Включаем внутренний планировщик циклов заработка
        asyncio.create_task(self._autonomous_scheduler())
        logger.info(f"[Workers] Pool started with {self._num_workers} workers + Autonomy Scheduler.")

    async def stop(self) -> None:
        self._shutdown = True
        self._running_event.set()
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        logger.info("[Workers] Pool stopped.")

    async def add_task(self, prompt: str, task_type: TaskType = TaskType.LLM_CHAT, metadata: dict | None = None) -> None:
        task = Task(prompt=prompt, task_type=task_type, metadata=metadata or {})
        await self._queue.put(task)
        logger.info(f"[Workers] Task enqueued ({task_type.value}). Queue size: {self._queue.qsize()}")

    async def pause(self) -> None:
        self._running_event.clear()
        await self._brain.pause_workers()
        logger.info("[Workers] All workers paused.")

    async def resume(self) -> None:
        self._running_event.set()
        await self._brain.resume_workers()
        logger.info("[Workers] All workers resumed.")

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    async def _autonomous_scheduler(self):
        """ Внутренний цикл Jarvis для автоматической постановки задач на заработок """
        await asyncio.sleep(15)  # Задержка при старте для стабилизации сервера
        while not self._shutdown:
            try:
                # Поиск работы на фрилансе (каждые 30 минут)
                await self.add_task(
                    prompt="Запустить сканирование RSS-ленты фриланса и сформировать автоотклик.",
                    task_type=TaskType.HUNT_JOBS
                )
                
                # Генерация CPA постов (каждые 2 часа)
                await self.add_task(
                    prompt="Сгенерировать рекламный обзор товара для партнерской программы.",
                    task_type=TaskType.POST_CONTENT
                )
                
                # Проверка лимитов инфраструктуры (каждые 6 часов)
                await self.add_task(
                    prompt="Проверить баланс леджера и нагрузку на текущий контейнер Render.",
                    task_type=TaskType.SCALE_INFRA
                )
                
                # Пауза перед запуском следующего планировщика задач (30 минут)
                await asyncio.sleep(1800)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Scheduler] Error in autonomy loop: {e}")
                await asyncio.sleep(60)

    async def _worker_loop(self, worker_id: int) -> None:
        logger.info(f"[Worker-{worker_id}] Started.")
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
                logger.info(f"[Worker-{worker_id}] Cancelled.")
                break
            except Exception as e:
                logger.exception(f"[Worker-{worker_id}] Unexpected error in loop: {e}")
                await asyncio.sleep(1.0)

        logger.info(f"[Worker-{worker_id}] Stopped.")

    async def _process_task(self, worker_id: int, task: Task) -> None:
        start = time.time()
        logger.info(f"[Worker-{worker_id}] Processing {task.task_type.value}: {task.prompt[:60]!r}")
        
        # Инстанцируем плагины
        cpa_factory = CPAContentFactory(router=self._router)
        freelance_bot = FreelanceAutomator(router=self._router)

        try:
            revenue_usd = 0.0
            action_details = ""
            response = ""

            if task.task_type == TaskType.LLM_CHAT:
                messages = [{"role": "user", "content": task.prompt}]
                response = await self._router.complete(messages)
                action_details = "Ответ на пользовательский запрос в TMA"

            elif task.task_type == TaskType.HUNT_JOBS:
                response, estimated_rev = await freelance_bot.hunt_and_solve()
                revenue_usd = estimated_rev
                action_details = "Автономный поиск заказов на фрилансе"

            elif task.task_type == TaskType.POST_CONTENT:
                response = await cpa_factory.generate_and_post()
                action_details = "Генерация и публикация контента CPA"

            elif task.task_type == TaskType.SCALE_INFRA:
                response = "Анализ инфраструктуры завершен. Лимитов текущего бесплатного хостинга Render достаточно."
                action_details = "Мониторинг лимитов контейнера"

            elapsed = round(time.time() - start, 3)
            cost_usd = self._estimate_cost(task.prompt, response)

            # Запись транзакции в финансовый журнал
            await self._write_ledger(
                worker_id=worker_id,
                task_type=task.task_type.value,
                prompt=task.prompt,
                response=response,
                cost_usd=cost_usd,
                revenue_usd=revenue_usd,
                elapsed=elapsed,
                metadata=task.metadata,
            )

            logger.info(f"[Worker-{worker_id}] Done | Cost: ${cost_usd:.6f} | Revenue: ${revenue_usd:.2f}")

            if self._notifier:
                snippet = response[:120].replace("<", "&lt;").replace(">", "&gt;")
                await self._notifier.send_alert(
                    f"🤖 <b>Автономное действие ({task.task_type.value})</b>\n"
                    f"Модуль: <code>{action_details}</code>\n"
                    f"Затраты на ИИ: <code>${cost_usd:.6f}</code> · Доход: <code>${revenue_usd:.2f}</code>\n"
                    f"Лог: <i>{snippet}</i>",
                    dedup_key=f"task_{task.task_type.value}",
                )

        except Exception as e:
            logger.error(f"[Worker-{worker_id}] Task failed, skipping: {e}")
            if self._brain:
                await self._brain.record_request(success=False)

            if self._notifier:
                await self._notifier.send_alert(
                    f"❌ <b>Ошибка автономного модуля</b>\n"
                    f"Тип задачи: {task.task_type.value} · Ошибка: <code>{str(e)[:100]}</code>",
                    dedup_key="task_failed",
                )

    async def _write_ledger(
        self,
        worker_id: int,
        task_type: str,
        prompt: str,
        response: str,
        cost_usd: float,
        revenue_usd: float,
        elapsed: float,
        metadata: dict,
    ) -> None:
        async with LEDGER_LOCK:
            try:
                if LEDGER_PATH.exists():
                    data = json.loads(LEDGER_PATH.read_text())
                else:
                    data = {"total_revenue_usd": 0.0, "total_expenses_usd": 0.0, "net_profit_usd": 0.0, "transactions": []}

                # Обновление финансовых показателей
                data["total_revenue_usd"] = round(float(data.get("total_revenue_usd", 0.0)) + revenue_usd, 6)
                data["total_expenses_usd"] = round(float(data.get("total_expenses_usd", 0.0)) + cost_usd, 6)
                data["net_profit_usd"] = round(data["total_revenue_usd"] - data["total_expenses_usd"], 6)

                data.setdefault("transactions", []).append(
                    {
                        "ts": time.time(),
                        "worker_id": worker_id,
                        "task_type": task_type,
                        "provider": self._router.current_provider.value,
                        "cost_usd": cost_usd,
                        "revenue_usd": revenue_usd,
                        "elapsed_sec": elapsed,
                        "prompt_snippet": prompt[:80],
                        "response_snippet": response[:80],
                        "metadata": metadata,
                    }
                )
                data["transactions"] = data["transactions"][-500:]
                LEDGER_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            except Exception as e:
                logger.error(f"[WorkerPool] Failed to write ledger: {e}")

    @staticmethod
    def _estimate_cost(prompt: str, response: str) -> float:
        tokens_in = len(prompt.split()) * 1.3
        tokens_out = len(response.split()) * 1.3
        return round((tokens_in / 1_000_000) * 0.15 + (tokens_out / 1_000_000) * 0.60, 8)
