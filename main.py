import asyncio
import logging
import os
from dotenv import load_dotenv

# Прямые импорты
from core.brain import brain
from core.fail_safe_routing import FailSafeRouter
from modules.admin_dashboard import start_bot
from modules.notifier import Notifier
from modules.tma_server import start_server
from modules.worker_pool import WorkerPool
from modules.core.jarvis_mind import JarvisMind
from modules.plugins.network_empire import NetworkEmpireManager, router as config_router

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis.main")

async def auto_post_scheduler(token):
    """Вынесенный изолированный планировщик автопостинга"""
    await asyncio.sleep(180)  # Ждем полной инициализации всех систем ядра
    while True:
        try:
            from aiogram import Bot
            logger.info("[Main-Scheduler] Инициализация теневого бота для пула империй...")
            
            # Явное создание экземпляра во избежание проблем с контекстными менеджерами aiogram в циклах
            shadow_bot = Bot(token=token)
            try:
                empire_manager = NetworkEmpireManager(shadow_bot)
                await empire_manager.auto_post_cycle()
            finally:
                # Гарантированное закрытие сессии бота для предотвращения утечек дескрипторов
                if hasattr(shadow_bot, "session") and shadow_bot.session and not shadow_bot.session.closed:
                    await shadow_bot.session.close()
                    
        except Exception as ex:
            # exc_info=True развернет полный Traceback в логах Render и покажет точную строку в network_empire.py
            logger.error(f"[Main-Scheduler] Критическая ошибка в цикле автопостинга: {ex}", exc_info=True)
            
        await asyncio.sleep(3 * 3600)  # Интервал запуска — 3 часа

async def main():
    logger.info("[Main] Starting services...")

    # Инициализация компонентов
    notifier = Notifier()
    router = FailSafeRouter(brain=brain, notifier=notifier)
    jarvis_mind = JarvisMind(ai_router=router, plugins_dir="modules/plugins")
    
    pool = WorkerPool(router=router, brain=brain, notifier=notifier, num_workers=3)
    await pool.start()

    # Запуск планировщика автопостинга, если есть токен
    target_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if target_token:
        asyncio.create_task(auto_post_scheduler(target_token))
    else:
        logger.warning("[Main-Scheduler] Токен бота не обнаружен в ENV. Автопостинг отключен.")

    # Запуск основных асинхронных сервисов
    bot_task = asyncio.create_task(
        start_bot(brain, pool=pool, notifier=notifier, jarvis_mind=jarvis_mind, empire_router=config_router)
    )
    server_task = asyncio.create_task(
        start_server(brain, pool=pool, notifier=notifier)
    )

    logger.info("[Main] All services running.")
    await asyncio.gather(bot_task, server_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[Main] Stopped.")
