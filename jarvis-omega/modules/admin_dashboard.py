import logging
import os
import time

from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger("jarvis.admin")


def create_admin_router(brain, pool=None, notifier=None, jarvis_mind=None):
    from aiogram import Router

    router = Router()
    try:
        admin_id = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
    except ValueError:
        admin_id = 0
        logger.error("[Admin] Invalid TELEGRAM_ADMIN_ID environment variable. Set to 0.")

    def is_admin(message: Message) -> bool:
        return message.from_user is not None and message.from_user.id == admin_id

    def _get_queue_size(worker_pool) -> str:
        """Безопасно вытаскивает размер очереди из пула воркеров."""
        if not worker_pool:
            return "N/A"
        
        # Перебираем возможные варианты названия атрибута очереди
        for attr_name in ['queue', '_queue', 'tasks', '_tasks']:
            q = getattr(worker_pool, attr_name, None)
            if q and hasattr(q, 'qsize'):
                try:
                    return str(q.qsize())
                except Exception:
                    pass
        
        # Если самой очереди как объекта нет, пробуем найти прямой метод пула
        for method_name in ['get_queue_size', 'qsize', 'size']:
            method = getattr(worker_pool, method_name, None)
            if method and callable(method):
                try:
                    return str(method())
                except Exception:
                    pass
                    
        return "Unknown"

    @router.message(Command("start"))
    async def cmd_start(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            "Jarvis-Omega Online\n"
            "Commands:\n"
            "/status   — system metrics\n"
            "/develop  — auto-development mode\n"
            "/pause    — pause workers\n"
            "/resume   — resume workers\n"
            "/queue    — queue size\n"
            "/alerts   — recent alerts"
        )

    @router.message(Command("status"))
    async def cmd_status(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        
        try:
            metrics = await brain.get_metrics()
        except Exception as e:
            logger.error(f"[Admin] Failed to get metrics from brain: {e}")
            metrics = None

        q_size = _get_queue_size(pool)
        queue_info = f"\nQueue size: {q_size}" if pool else ""
        
        if metrics:
            text = (
                f"System Status\n"
                f"Uptime: {metrics.get('uptime_seconds', 'N/A')}s\n"
                f"Provider: {metrics.get('active_provider', 'N/A')}\n"
                f"Provider switches: {metrics.get('provider_switches', 'N/A')}\n"
                f"Requests total: {metrics.get('requests_total', 'N/A')}\n"
                f"Success rate: {metrics.get('success_rate', 'N/A')}%\n"
                f"Failed: {metrics.get('requests_failed', 'N/A')}\n"
                f"Workers paused: {metrics.get('workers_paused', 'N/A')}\n"
                f"Profit: ${metrics.get('profit_usd', 0.0):.4f}"
                f"{queue_info}"
            )
        else:
            text = f"System Status\nBrain metrics unavailable.{queue_info}"
            
        await message.answer(text)

    # --- ХЭНДЛЕР САМОРАЗВИТИЯ ДЖАРВИСА ---
    @router.message(Command("develop", "upgrade"))
    async def cmd_develop(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return

        if not jarvis_mind:
            await message.answer("❌ Ошибка: Модуль JarvisMind не подключен к роутеру.")
            return

        task = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
        
        if not task:
            await message.answer(
                "🤖 **Режим саморазвития Джарвиса**\n\n"
                "Напиши мне, какую функцию или плагин разработать. Пример:\n"
                "`/develop Сделай парсер, который запрашивает курс TON к USD и возвращает текст`"
            )
            return

        await message.answer(
            "🧠 *Джарвис ушел в подсознание...*\n"
            "Анализирую архитектуру, пишу тестовый код и проверяю его безопасность. Подожди немного..."
        )
        
        try:
            result = await jarvis_mind.self_develop(task)
            await message.answer(result, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"[Admin] Self-develop error: {e}")
            await message.answer(f"❌ Ошибка в процессе генерации кода: {e}")

    @router.message(Command("pause"))
    async def cmd_pause(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        if pool:
            await pool.pause()
        else:
            await brain.pause_workers()
        await message.answer("Workers paused.")
        logger.info(f"[Admin] Workers paused by admin {admin_id}")

    @router.message(Command("resume"))
    async def cmd_resume(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        if pool:
            await pool.resume()
        else:
            await brain.resume_workers()
        await message.answer("Workers resumed.")
        logger.info(f"[Admin] Workers resumed by admin {admin_id}")

    @router.message(Command("queue"))
    async def cmd_queue(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        q_size = _get_queue_size(pool)
        await message.answer(f"Queue size: {q_size} pending tasks.")

    @router.message(Command("alerts"))
    async def cmd_alerts(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        if not notifier:
            await message.answer("Notifier not available.")
            return
        try:
            history = notifier.get_history()
        except Exception as e:
            await message.answer(f"Error fetching alerts: {e}")
            return
            
        if not history:
            await message.answer("No alerts sent yet.")
            return
        lines = [f"Recent Alerts ({len(history)}):"]
        for record in history:
            dt = time.strftime("%d.%m %H:%M:%S", time.localtime(record.ts))
            first_line = record.text.split("\n")[0] if record.text else ""
            clean = (
                first_line
                .replace("<b>", "").replace("</b>", "")
                .replace("<code>", "").replace("</code>", "")
                .replace("<i>", "").replace("</i>", "")
            )
            lines.append(f"[{dt}] {clean}")
        await message.answer("\n".join(lines))

    return router


async def start_bot(brain, pool=None, notifier=None, jarvis_mind=None):
    from aiogram import Bot, Dispatcher

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment.")

    bot = Bot(token=token)
    dp = Dispatcher()
    
    dp.include_router(create_admin_router(brain, pool=pool, notifier=notifier, jarvis_mind=jarvis_mind))

    logger.info("[Admin] Starting Telegram bot polling...")
    await dp.start_polling(bot)
