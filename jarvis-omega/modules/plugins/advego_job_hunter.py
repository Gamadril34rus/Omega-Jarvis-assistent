import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

logger = logging.getLogger("jarvis.plugins.advego_jobs")

class AdvegoJobHunter:
    def __init__(self, router):
        self._router = router
        self._login = "zmey1341@mail.ru"
        self._password = "Samsung777+"
        self._static_dir = Path(__file__).resolve().parents[2] / "static"

    async def hunt_and_execute(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Применяем stealth, чтобы скрыть признаки автоматизации
            await stealth_async(page)

            try:
                logger.info("Переход на Advego (stealth mode)...")
                await page.goto("https://advego.com/login/", wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # Ввод логина и пароля
                await page.fill('input[name="login"]', self._login)
                await page.fill('input[name="password"]', self._password)
                
                # Клик по кнопке входа
                await page.click('button[type="submit"]')
                await asyncio.sleep(7) 
                
                # Проверка авторизации по наличию специфических элементов профиля
                if not await page.query_selector('.user-profile-menu, .header__user'):
                    await page.screenshot(path=str(self._static_dir / "advego_error.png"))
                    raise Exception("Не удалось пройти авторизацию (возможно капча)")

                logger.info("Авторизация успешна!")
                await page.goto("https://advego.com/job/find/?job_type=1&job_type=2")
                await asyncio.sleep(3)
                
                # Поиск заказа
                job_items = await page.query_selector_all('.job_item')
                if not job_items:
                    return "Заказов пока нет", 0.0

                take_link = await job_items[0].query_selector('a.job_take_link')
                if take_link:
                    await take_link.click()
                    return "Заказ успешно взят!", 150.0
                
                return "Заказы найдены, но их нельзя взять", 0.0

            except Exception as e:
                logger.error(f"Ошибка Advego: {e}")
                return f"Сбой: {str(e)}", 0.0
            finally:
                await context.close()
                await browser.close()
