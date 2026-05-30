import logging
import os
import time
import html

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
        if not worker_pool:
            return "N/A"
        for attr_name in ['queue', '_queue', 'tasks', '_tasks']:
            q = getattr(worker_pool, attr_name, None)
            if q and hasattr(q, 'qsize'):
                try:
                    return str(q.qsize())
                except Exception:
                    pass
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
                "🤖 <b>Режим саморазвития Джарвиса</b>\n\n"
                "Напиши мне, какую функцию или плагин разработать. Пример:\n"
                "<code>/develop Сделай парсер, который запрашивает курс TON к USD</code>",
                parse_mode="HTML"
            )
            return

        await message.answer(
            "🧠 <i>Джарвис ушел в подсознание...</i>\n"
            "Анализирую архитектуру, пишу тестовый код и проверяю его безопасность. Подожди немного...",
            parse_mode="HTML"
        )
        try:
            result = await jarvis_mind.self_develop(task)
            if "```python" in result:
                parts = result.split("```python")
                intro = html.escape(parts[0].strip())
                code_and_rest = parts[1].split("```")
                code_block = html.escape(code_and_rest[0].strip())
                outro = html.escape(code_and_rest[1].strip()) if len(code_and_rest) > 1 else ""
                formatted_text = f"{intro}\n\n<pre><code class='language-python'>{code_block}</code></pre>\n\n{outro}"
            else:
                formatted_text = html.escape(result)

            try:
                await message.answer(formatted_text, parse_mode="HTML")
            except Exception as parse_err:
                logger.warning(f"[Admin] HTML parse failed, falling back to raw text: {parse_err}")
                await message.answer(f"🤖 Отчет (сырой текст):\n\n{result}", parse_mode=None)
        except Exception as e:
            logger.error(f"[Admin] Self-develop error: {e}")
            await message.answer(f"❌ Критическая ошибка в процессе генерации кода: {e}")

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
            clean = first_line.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", "")
            lines.append(f"[{dt}] {clean}")
        await message.answer("\n".join(lines))

    return router


async def start_bot(brain, pool=None, notifier=None, jarvis_mind=None, empire_router=None):
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    # Оригинальная чистая логика админки
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в переменных окружения.")

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключаем роутер админки
    dp.include_router(create_admin_router(brain, pool=pool, notifier=notifier, jarvis_mind=jarvis_mind))
    logger.info("[Admin] Роутер админки успешно подключен.")

    # Если передан роутер империи — регистрируем его в основном диспетчере
    if empire_router:
        dp.include_router(empire_router)
        logger.info("[Admin] Роутер империи сетевых каналов ЖЕСТКО внедрен в Диспетчер.")

    logger.info("[Admin] Starting Telegram bot polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception(f"[Admin] Критическая ошибка при поллинге бота: {e}")
    finally:
        await bot.session.close()
