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
        self.username = os.getenv("ADVEGO_USERNAME", "")
        self.password = os.getenv("ADVEGO_PASSWORD", "")
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
        logger.info("[Advego] Запуск сессии сканирования...")
        
        if not self.username or not self.password:
            logger.error("[Advego] Переменные окружения ADVEGO_USERNAME или ADVEGO_PASSWORD не заданы!")
            return "Ошибка: учетные данные Advego не настроены.", 0.0

        async with async_playwright() as p:
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
            ]
            
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-position=0,0",
                    "--ignore-certificate-errors"
                ]
            )
            
            context = await browser.new_context(
                user_agent=random.choice(user_agents),
                viewport={"width": 1366, "height": 768},
                locale="ru-RU",
                timezone_id="Europe/Moscow"
            )
            
            page = await context.new_page()
            
            # Скрываем присутствие автоматизации webdriver
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
            """)

            try:
                # 1. Переходим на страницу авторизации
                logger.info("[Advego] Переход на страницу авторизации...")
                await page.goto("https://advego.com/login/", wait_until="networkidle", timeout=30000)
                await asyncio.sleep(random.uniform(2.0, 4.0))

                # Проверяем на Cloudflare
                title = await page.title()
                content = await page.content()
                
                if "Cloudflare" in title or "Just a moment" in title or "checking your browser" in content.lower():
                    logger.warning("[Advego] Обнаружена защита Cloudflare! Фиксация состояния.")
                    await self._safe_screenshot(page, "cloudflare_blocked.png")
                    await browser.close()
                    return "Заблокировано Cloudflare на этапе входа.", 0.0

                # 2. Поиск полей формы логина
                logger.info("[Advego] Проверка доступности формы авторизации...")
                try:
                    email_input = await page.wait_for_selector('input[name="email"], input[type="email"]', timeout=7000)
                    password_input = await page.wait_for_selector('input[name="password"], input[type="password"]', timeout=7000)
                except Exception:
                    await self._safe_screenshot(page, "login_form_missing.png")
                    logger.error("[Advego] Форма входа не найдена. Изменилась верстка сайта.")
                    await browser.close()
                    return "Ошибка: Изменилась верстка сайта Advego, поля ввода не найдены.", 0.0

                # 3. Имитируем ввод текста человеком
                logger.info("[Advego] Заполнение учетных данных...")
                await email_input.click()
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await page.keyboard.type(self.username, delay=random.uniform(50, 120))
                
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
                await password_input.click()
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await page.keyboard.type(self.password, delay=random.uniform(60, 130))
                
                await asyncio.sleep(random.uniform(0.8, 1.5))

                submit_button = await page.wait_for_selector('button[type="submit"], input[type="submit"], .btn-action', timeout=5000)
                await submit_button.click()
                
                logger.info("[Advego] Ожидание авторизации...")
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(3.0)

                # Проверяем успешность входа
                current_html = await page.content()
                if "logout" in current_html.lower() or "выход" in current_html.lower() or "user" in page.url:
                    logger.info("[Advego] Авторизация успешно пройдена!")
                else:
                    await self._safe_screenshot(page, "login_failed_wrong_credentials.png")
                    logger.warning("[Advego] Не удалось войти. Неверные данные или скрытая капча.")
                    await browser.close()
                    return "Ошибка авторизации: неверный логин/пароль или скрытая капча.", 0.0

                # 4. Переход в ленту заказов
                logger.info("[Advego] Переход в ленту заказов...")
                await page.goto("https://advego.com/job/find/", wait_until="networkidle")
                await asyncio.sleep(2.0)
                
                await self._safe_screenshot(page, "advego_jobs_feed.png")
                
                logger.info("[Advego] Сканирование успешно завершено.")
                await browser.close()
                return "Сканирование ленты Advego завершено успешно. Подходящих заказов не найдено.", 0.0

            except Exception as e:
                # Глобальный перехватчик ошибок сессии
                logger.error(f"[Advego] Критический сбой во время сессии: {e}")
                await self._safe_screenshot(page, "advego_fatal_error.png")
                await browser.close()
                return f"Критическая ошибка сессии: {e}", 0.0

async def run_plugin() -> str:
    """Интерфейсная функция для тестирования плагина ядром JarvisMind"""
    hunter = AdvegoJobHunter()
    result, revenue = await hunter.hunt_and_execute()
    return f"Статус: {result} | Доход: {revenue} USD"
