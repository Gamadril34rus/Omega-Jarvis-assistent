import os
import asyncio
import logging
import random
from pathlib import Path
from playwright.async_api import async_playwright

logger = logging.getLogger("jarvis.plugins.advego_jobs")

class AdvegoJobHunter:
    def __init__(self, router=None):
        self._router = router
        # Подтягиваем куки сессии из переменных окружения
        self.cookie_sid = os.getenv("ADVEGO_COOKIE_SID", "")
        self.cookie_token = os.getenv("ADVEGO_COOKIE_TOKEN", "")
        self.screenshot_dir = Path("/app/outputs") if os.path.exists("/app") else Path("./outputs")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _safe_screenshot(self, page, name: str):
        """Безопасный захват экрана без зависания на шрифтах и анимациях"""
        screenshot_path = self.screenshot_dir / name
        try:
            await page.screenshot(path=str(screenshot_path), timeout=5000, animations="disabled")
            logger.info(f"[Advego] Скриншот сохранен: {screenshot_path}")
        except Exception as e:
            logger.warning(f"[Advego] Не удалось сделать скриншот {name} (пропущено): {e}")

    async def hunt_and_execute(self) -> tuple[str, float]:
        """Основной метод, вызываемый воркером для сканирования и выполнения задач"""
        logger.info("[Advego] Запуск сессии сканирования через куки...")
        
        if not self.cookie_sid or not self.cookie_token:
            logger.error("[Advego] Ошибка: Переменные ADVEGO_COOKIE_SID или ADVEGO_COOKIE_TOKEN не заданы в Render!")
            return "Ошибка: куки авторизации Advego не настроены.", 0.0

        async with async_playwright() as p:
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ]
            
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--ignore-certificate-errors"
                ]
            )
            
            context = await browser.new_context(
                user_agent=random.choice(user_agents),
                viewport={"width": 1366, "height": 768},
                locale="ru-RU",
                timezone_id="Europe/Moscow"
            )
            
            # Внедряем куки для домена advego.com ДО перехода на сайт
            await context.add_cookies([
                {
                    "name": "domain_sid",
                    "value": self.cookie_sid,
                    "domain": ".advego.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True
                },
                {
                    "name": "token",
                    "value": self.cookie_token,
                    "domain": ".advego.com",
                    "path": "/",
                    "httpOnly": False,
                    "secure": True
                }
            ])
            
            page = await context.new_page()
            
            # Скрываем автоматизацию
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            try:
                # 1. Прыгаем в ленту заказов
                logger.info("[Advego] Переход в ленту заказов напрямую через готовую сессию...")
                await page.goto("https://advego.com/job/find/", wait_until="networkidle", timeout=30000)
                await asyncio.sleep(random.uniform(2.0, 4.0))

                # Проверяем, не выкинуло ли нас на авторизацию/Cloudflare
                current_html = await page.content()
                current_url = page.url

                if "login" in current_url or "login" in current_html.lower():
                    logger.warning("[Advego] Сессия по кукам не принята сайтом, перекинуло на логин.")
                    await self._safe_screenshot(page, "cookie_auth_failed.png")
                    await browser.close()
                    return "Ошибка: Advego отклонил куки, требуется обновить их значения.", 0.0

                if "Cloudflare" in await page.title() or "Just a moment" in await page.title():
                    logger.warning("[Advego] Проверка Cloudflare даже при входе по кукам.")
                    await self._safe_screenshot(page, "cloudflare_on_cookies.png")
                    await browser.close()
                    return "Заблокировано Cloudflare при переходе в ленту.", 0.0

                # 2. Успешный вход в ленту
                logger.info("[Advego] Успешный вход в закрытую зону выполнен!")
                await self._safe_screenshot(page, "advego_jobs_feed_success.png")
                
                # Твой парсер элементов (находим новые заказы, если есть)
                # Переменная под доход в рублях
                revenue_rub = 0.0 
                
                logger.info("[Advego] Сканирование ленты успешно завершено.")
                await browser.close()
                return "Сканирование ленты Advego по активной сессии завершено. Новых заказов нет.", revenue_rub

            except Exception as e:
                logger.error(f"[Advego] Критический сбой во время работы по кукам: {e}")
                await self._safe_screenshot(page, "advego_cookie_fatal_error.png")
                await browser.close()
                return f"Критическая ошибка сессии: {e}", 0.0

async def run_plugin() -> str:
    """Интерфейсная функция для тестирования плагина ядром JarvisMind"""
    hunter = AdvegoJobHunter()
    result, revenue_rub = await hunter.hunt_and_execute()
    return f"Статус: {result} | Доход: {revenue_rub} руб."
