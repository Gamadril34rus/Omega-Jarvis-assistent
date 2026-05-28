import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright

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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            try:
                logger.info("Переход на Advego...")
                await page.goto("https://advego.com/login/", wait_until="domcontentloaded")
                await asyncio.sleep(4)

                # Используем JavaScript для заполнения, это обходит проблему видимости Playwright
                logger.info("Ввод данных через JS...")
                await page.evaluate(f"""
                    () => {{
                        const emailInput = document.querySelector('input[name="login"], #login_email, input[type="email"]');
                        const passInput = document.querySelector('input[name="password"], #login_password');
                        if (emailInput) emailInput.value = '{self._login}';
                        if (passInput) passInput.value = '{self._password}';
                        
                        // Пытаемся найти кнопку входа и кликнуть по ней
                        const submitBtn = document.querySelector('button[type="submit"], .btn_orange');
                        if (submitBtn) submitBtn.click();
                    }}
                """)
                
                await asyncio.sleep(6) # Ждем обработки формы

                # Проверка, залогинились ли мы
                if "login" in page.url:
                    logger.warning("Похоже, мы все еще на странице логина. Проверяем наличие ошибок...")
                    raise Exception("Не удалось авторизоваться")

                logger.info("Авторизация успешна. Переход к заказам...")
                await page.goto("https://advego.com/job/find/?job_type=1&job_type=2")
                await asyncio.sleep(3)
                
                # Работа с заказами
                job_items = await page.query_selector_all('.job_item')
                if not job_items:
                    return "Заказов пока нет", 0.0

                # Берем первый доступный заказ
                take_link = await job_items[0].query_selector('a.job_take_link')
                if take_link:
                    await take_link.click()
                    return "Заказ успешно взят в работу!", 150.0
                
                return "Заказы есть, но взять нельзя (тендеры)", 0.0

            except Exception as e:
                logger.error(f"Ошибка в работе Advego: {e}")
                if self._static_dir.exists():
                    await page.screenshot(path=str(self._static_dir / "advego_error.png"))
                return f"Ошибка: {str(e)}", 0.0
            finally:
                await context.close()
                await browser.close()
