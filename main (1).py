import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Жесткий поиск корня проекта и всех поддиректорий
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

for root, dirs, files in os.walk(current_dir):
    if "modules" in dirs:
        if root not in sys.path:
            sys.path.insert(0, root)
        break

try:
    from modules.core.jarvis_mind import JarvisMind
except ModuleNotFoundError:
    try:
        from core.jarvis_mind import JarvisMind
    except ModuleNotFoundError:
        sys.path.append(os.path.join(current_dir, "jarvis-omega"))
        from modules.core.jarvis_mind import JarvisMind

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("jarvis.main")


async def main():
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
    logger.info("[Main] FailSafeRouter initialized. Cascade: Gemini → OpenAI → Zhipu → OpenRouter → Ollama")

    jarvis_mind = JarvisMind(ai_router=router, plugins_dir="/app/modules/plugins")
    logger.info("[Main] JarvisMind (Ядро саморазвития) успешно запущено.")

    pool = WorkerPool(router=router, brain=brain, notifier=notifier, num_workers=3)
    await pool.start()
    logger.info("[Main] WorkerPool started with 3 workers.")

    # --- ИЗОЛИРОВАННЫЙ ПЛАНИРОВЩИК ИМПЕРИИ КАНАЛОВ ---
    empire_router = None
    target_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    
    if target_token:
        try:
            # Сквозной тотальный перебор путей для импорта менеджера и роутера империи
            try:
                from modules.plugins.network_empire import NetworkEmpireManager, router as config_router
                logger.info("[Main-Import] Успешный импорт из modules.plugins.network_empire")
            except ModuleNotFoundError:
                try:
                    from plugins.network_empire import NetworkEmpireManager, router as config_router
                    logger.info("[Main-Import] Успешный импорт из plugins.network_empire")
                except ModuleNotFoundError:
                    try:
                        from jarvis_omega.modules.plugins.network_empire import NetworkEmpireManager, router as config_router
                        logger.info("[Main-Import] Успешный импорт из jarvis_omega.modules.plugins.network_empire")
                    except ModuleNotFoundError:
                        # Самый жесткий вариант: принудительно пихаем директорию плагинов в sys.path
                        import sys
                        possible_paths = [
                            os.path.join(current_dir, "modules", "plugins"),
                            os.path.join(current_dir, "jarvis-omega", "modules", "plugins"),
                            os.path.join(current_dir, "plugins")
                        ]
                        for p in possible_paths:
                            if os.path.exists(p):
                                sys.path.append(p)
                        
                        from network_empire import NetworkEmpireManager, router as config_router
                        logger.info("[Main-Import] Успешный импорт напрямую через аварийный sys.path")
            
            empire_router = config_router
            
            async def auto_post_scheduler(token):
                from aiogram import Bot
                logger.info("[Main-Scheduler] Фоновый таймер сети каналов ожидает 3 минуты перед стартом...")
                await asyncio.sleep(180)
                logger.info("[Main-Scheduler] Фоновый таймер сети каналов запущен.")
                
                while True:
                    try:
                        async with Bot(token=token) as shadow_bot:
                            empire_manager = NetworkEmpireManager(shadow_bot)
                            logger.info("[Main-Scheduler] Время публикации. Будем парсер...")
                            await empire_manager.auto_post_cycle()
                    except Exception as ex:
                        logger.error(f"[Main-Scheduler Ошибка] Сбой в цикле автопостинга: {ex}")
                    await asyncio.sleep(3 * 3600)
            
            asyncio.create_task(auto_post_scheduler(target_token), name="network-empire-scheduler")
            logger.info("[Main] Задача планировщика автопостинга добавлена в асинхронный пул.")
            
        except Exception as plugin_err:
            logger.error(f"[Main] Не удалось запустить планировщик каналов: {plugin_err}")
    # -------------------------------------------------

    bot_task = asyncio.create_task(
        start_bot(brain, pool=pool, notifier=notifier, jarvis_mind=jarvis_mind, empire_router=empire_router), 
        name="telegram-bot"
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
        logger.info("[Main] WorkerPool stopped on exit.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[Main] Interrupted by user. Exiting.")
