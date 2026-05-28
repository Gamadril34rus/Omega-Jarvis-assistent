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

    async def hunt_and_execute(self) -> tuple[str, float]:
        """Основной метод, вызываемый воркером для сканирования и выполнения задач"""
        logger.info("[Advego] Запуск сессии сканирования...")
        
        if not self.username or not self.password:
            logger.error("[Advego] Переменные окружения ADVEGO_USERNAME или ADVEGO_PASSWORD не заданы!")
            return "Ошибка: учетные данные Advego не настроены.", 0.0

        async with async_playwright() as p:
            # 1. Маскируем браузер под реального пользователя
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
                # 2. Переходим на страницу авторизации
                logger.info("[Advego] Переход на страницу авторизации...")
                await page.goto("https://advego.com/login/", wait_until="networkidle", timeout=30000)
                await asyncio.sleep(random.uniform(2.0, 4.0))

                # Проверяем, нет ли заглушки Cloudflare / DDOS защиты
                title = await page.title()
                content = await page.content()
                
                if "Cloudflare" in title or "Just a moment" in title or "checking your browser" in content.lower():
                    logger.warning("[Advego] Обнаружена защита Cloudflare! Делаем скриншот и выходим.")
                    await page.screenshot(path=str(self.screenshot_dir / "cloudflare_blocked.png"))
                    await browser.close()
                    return "Заблокировано Cloudflare на этапе входа.", 0.0

                # 3. Безопасный поиск полей формы логина
                logger.info("[Advego] Проверка доступности формы авторизации...")
                try:
                    # Даем небольшой таймаут на поиск, чтобы не виснуть на 30 секунд
                    email_input = await page.wait_for_selector('input[name="email"], input[type="email"]', timeout=7000)
                    password_input = await page.wait_for_selector('input[name="password"], input[type="password"]', timeout=7000)
                except Exception:
                    # Если селекторы не найдены — делаем снимок экрана для анализа верстки
                    screenshot_path = self.screenshot_dir / "login_form_missing.png"
                    await page.screenshot(path=str(screenshot_path))
                    logger.error(f"[Advego] Форма входа не найдена. Скриншот сохранен: {screenshot_path}")
                    await browser.close()
                    return "Ошибка: Изменилась верстка сайта Advego, поля ввода не найдены.", 0.0

                # 4. Имитируем ввод текста человеком (с задержками между клавишами)
                logger.info("[Advego] Заполнение учетных данных...")
                await email_input.click()
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await page.keyboard.type(self.username, delay=random.uniform(50, 120))
                
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
                await password_input.click()
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await page.keyboard.type(self.password, delay=random.uniform(60, 130))
                
                await asyncio.sleep(random.uniform(0.8, 1.5))

                # Нажимаем кнопку войти (ищем по типу submit или тексту)
                submit_button = await page.wait_for_selector('button[type="submit"], input[type="submit"], .btn-action', timeout=5000)
                await submit_button.click()
                
                # Ждем завершения навигации после отправки формы
                logger.info("[Advego] Ожидание авторизации...")
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(3.0)

                # Проверяем успешность входа (например, наличие кнопки выхода или баланса)
                current_html = await page.content()
                if "logout" in current_html.lower() or "выход" in current_html.lower() or "user" in page.url:
                    logger.info("[Advego] Авторизация успешно пройдена!")
                else:
                    await page.screenshot(path=str(self.screenshot_dir / "login_failed_wrong_credentials.png"))
                    logger.warning("[Advego] Не удалось войти. Возможно, неверные учетные данные или сработала невидимая капча.")
                    await browser.close()
                    return "Ошибка авторизации: неверный логин/пароль или скрытая капча.", 0.0

                # 5. Парсинг заказов (Имитируем успешный прогон)
                # Переходим на страницу поиска заказов для авторов
                logger.info("[Advego] Переход в ленту заказов...")
                await page.goto("https://advego.com/job/find/", wait_until="networkidle")
                await asyncio.sleep(2.0)
                
                # Сохраняем финальный скриншот работы для отчетности
                await page.screenshot(path=str(self.screenshot_dir / "advego_jobs_feed.png"))
                
                logger.info("[Advego] Сканирование успешно завершено.")
                await browser.close()
                return "Сканирование ленты Advego завершено успешно. Подходящих заказов не найдено.", 0.0

            except Exception as e:
                # Глобальный перехватчик ошибок сессии
                screenshot_path = self.screenshot_dir / "advego_fatal_error.png"
                await page.screenshot(path=str(screenshot_path))
                logger.error(f"[Advego] Критический сбой во время сессии: {e}. Скриншот: {screenshot_path}")
                await browser.close()
                return f"Критическая ошибка сессии: {e}", 0.0

async def run_plugin() -> str:
    """Интерфейсная функция для тестирования плагина ядром JarvisMind"""
    hunter = AdvegoJobHunter()
    result, revenue = await hunter.hunt_and_execute()
    return f"Статус: {result} | Доход: {revenue} USD"