import os
import sys

# Жесткий поиск корня проекта и всех поддиректорий
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Дополнительно сканируем подпапки на случай, если Render создал вложенную структуру
for root, dirs, files in os.walk(current_dir):
    if "modules" in dirs:
        modules_path = os.path.join(root, "modules")
        if root not in sys.path:
            sys.path.insert(0, root)
        break

# Пытаемся импортировать через абсолютный и относительный пути (Failsafe импорт)
try:
    from modules.core.jarvis_mind import JarvisMind
except ModuleNotFoundError:
    try:
        # Если папка modules оказалась в корне выполнения напрямую
        from core.jarvis_mind import JarvisMind
    except ModuleNotFoundError:
        # Если структура застряла внутри вложенной директории jarvis-omega
        sys.path.append(os.path.join(current_dir, "jarvis-omega"))
        from modules.core.jarvis_mind import JarvisMind

import asyncio
import logging

from dotenv import load_dotenv
from aiogram import Bot

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("jarvis.main")


async def main():
    # Импорты остальных модулей с защитой от сбоя путей
    try:
        from core.brain import brain
        from core.fail_safe_routing import FailSafeRouter
        from modules.admin_dashboard import start_bot
        from modules.notifier import Notifier
        from modules.tma_server import start_server
        from modules.worker_pool import WorkerPool
    except ModuleNotFoundError:
        from jarvis_omega.core.brain import brain
        from jarvis_omega.core.fail_safe_routing import FailSafeRouter
        from jarvis_omega.modules.admin_dashboard import start_bot
        from jarvis_omega.modules.notifier import Notifier
        from jarvis_omega.modules.tma_server import start_server
        from jarvis_omega.modules.worker_pool import WorkerPool

    notifier = Notifier()
    logger.info("[Main] Notifier initialized (cooldown: 5 min per alert key).")

    router = FailSafeRouter(brain=brain, notifier=notifier)
    logger.info(
        "[Main] FailSafeRouter initialized. "
        "Cascade: Gemini → OpenAI → Zhipu → OpenRouter → Ollama"
    )

    # Инициализация модуля мышления и саморазвития Джарвиса
    jarvis_mind = JarvisMind(ai_router=router, plugins_dir="/app/modules/plugins")
    logger.info("[Main] JarvisMind (Ядро саморазвития) успешно запущено.")

    pool = WorkerPool(router=router, brain=brain, notifier=notifier, num_workers=3)
    await pool.start()
    logger.info("[Main] WorkerPool started with 3 workers.")

    # --- ИНТЕГРАЦИЯ ПЛАНИРОВЩИКА СЕТИ КАНАЛОВ ---
    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    empire_bot = None
    empire_router = None
    
    if bot_token:
        try:
            try:
                from modules.plugins.network_empire import NetworkEmpireManager, router as config_router
            except ModuleNotFoundError:
                try:
                    from jarvis_omega.modules.plugins.network_empire import NetworkEmpireManager, router as config_router
                except ModuleNotFoundError:
                    from plugins.network_empire import NetworkEmpireManager, router as config_router
            
            empire_router = config_router
            # Создаем выделенный клиент для рассылки постов в каналы
            empire_bot = Bot(token=bot_token)
            empire_manager = NetworkEmpireManager(empire_bot)
            
            async def auto_post_scheduler():
                logger.info("[Main-Scheduler] Фоновый таймер сети каналов успешно запущен.")
                # Даем системе 3 минуты (180 сек), чтобы поднять основные процессы
                await asyncio.sleep(180)
                while True:
                    try:
                        logger.info("[Main-Scheduler] Время публикации. Будем парсер...")
                        await empire_manager.auto_post_cycle()
                    except Exception as ex:
                        logger.error(f"[Main-Scheduler Ошибка] Сбой в цикле автопостинга: {ex}")
                    
                    # Интервал — раз в 3 часа
                    await asyncio.sleep(3 * 3600)
            
            # Запускаем бесконечный цикл планировщика параллельной фоновой задачей
            asyncio.create_task(auto_post_scheduler(), name="network-empire-scheduler")
            logger.info("[Main] Задача планировщика автопостинга добавлена в асинхронный пул.")
            
        except Exception as plugin_err:
            logger.error(f"[Main] Не удалось запустить планировщик каналов: {plugin_err}")
    else:
        logger.warning("[Main] Переменная BOT_TOKEN/TELEGRAM_BOT_TOKEN отсутствует. Сеть каналов не будет обновляться.")
    # --------------------------------------------

    # Передаем созданный jarvis_mind и роутер империи внутрь единой таски телеграм-бота
    bot_task = asyncio.create_task(
        start_bot(brain, pool=pool, notifier=notifier, jarvis_mind=jarvis_mind, empire_router=empire_router), name="telegram-bot"
    )
    server_task = asyncio.create_task(
        start_server(brain, pool=pool, notifier=notifier), name="tma-server"
    )

    logger.info("[Main] All services running: bot + TMA server + 3 workers + notifier.")

    try:
        await asyncio.gather(bot_task, server_task)
    except asyncio.CancelledError:
        logger.info("[Main] Shutdown requested.")
    except Exception as e:
        logger.exception(f"[Main] Fatal error: {e}")
        raise
    finally:
        await pool.stop()
        if empire_bot:
            await empire_bot.session.close()
            logger.info("[Main] Фоновая сессия Bot для каналов успешно закрыта.")
        logger.info("[Main] WorkerPool stopped on exit.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[Main] Interrupted by user. Exiting.")
