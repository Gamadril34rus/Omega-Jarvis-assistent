import logging
import os
import time

from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger("jarvis.admin")


def create_admin_router(brain, pool=None, notifier=None):
    from aiogram import Router

    router = Router()
    admin_id = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))

    def is_admin(message: Message) -> bool:
        return message.from_user is not None and message.from_user.id == admin_id

    @router.message(Command("start"))
    async def cmd_start(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            "Jarvis-Omega Online\n"
            "Commands:\n"
            "/status — system metrics\n"
            "/pause  — pause workers\n"
            "/resume — resume workers\n"
            "/queue  — queue size\n"
            "/alerts — recent alerts"
        )

    @router.message(Command("status"))
    async def cmd_status(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        metrics = await brain.get_metrics()
        queue_info = f"\nQueue size: {pool.queue_size}" if pool else ""
        text = (
            f"System Status\n"
            f"Uptime: {metrics['uptime_seconds']}s\n"
            f"Provider: {metrics['active_provider']}\n"
            f"Provider switches: {metrics['provider_switches']}\n"
            f"Requests total: {metrics['requests_total']}\n"
            f"Success rate: {metrics['success_rate']}%\n"
            f"Failed: {metrics['requests_failed']}\n"
            f"Workers paused: {metrics['workers_paused']}\n"
            f"Profit: ${metrics['profit_usd']:.4f}"
            f"{queue_info}"
        )
        await message.answer(text)

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
        size = pool.queue_size if pool else 0
        await message.answer(f"Queue size: {size} pending tasks.")

    @router.message(Command("alerts"))
    async def cmd_alerts(message: Message):
        if not is_admin(message):
            await message.answer("Access denied.")
            return
        if not notifier:
            await message.answer("Notifier not available.")
            return
        history = notifier.get_history()
        if not history:
            await message.answer("No alerts sent yet.")
            return
        lines = [f"Recent Alerts ({len(history)}):"]
        for record in history:
            dt = time.strftime("%d.%m %H:%M:%S", time.localtime(record.ts))
            first_line = record.text.split("\n")[0]
            clean = (
                first_line
                .replace("<b>", "").replace("</b>", "")
                .replace("<code>", "").replace("</code>", "")
                .replace("<i>", "").replace("</i>", "")
            )
            lines.append(f"[{dt}] {clean}")
        await message.answer("\n".join(lines))

    return router


async def start_bot(brain, pool=None, notifier=None):
    from aiogram import Bot, Dispatcher

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment.")

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(create_admin_router(brain, pool=pool, notifier=notifier))

    logger.info("[Admin] Starting Telegram bot polling...")
    await dp.start_polling(bot)
