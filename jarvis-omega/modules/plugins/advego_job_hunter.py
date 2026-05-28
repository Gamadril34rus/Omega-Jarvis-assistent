import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger("jarvis.plugins.advego_jobs")

class AdvegoJobHunter:
    def __init__(self, router):
        self._router = router
        # Твои данные из профиля
        self._login = "zmey1341@mail.ru"
        self._password = "Samsung777+"

    async def hunt_and_execute(self):
        async with async_playwright() as p:
            # Запуск в режиме без окна (для сервера Render)
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # 1. Авторизация
                await page.goto("https://advego.com/login/")
                await page.fill('input[name="email"]', self._login)
                await page.fill('input[name="password"]', self._password)
                await page.click('button[type="submit"]')
                await asyncio.sleep(5) # Пауза, чтобы сайт не забанил за скорость

                # 2. Поиск доступных заказов (Копирайтинг и Рерайт)
                await page.goto("https://advego.com/job/find/?job_type=1&job_type=2")
                
                # Ищем кнопку "Взять в работу"
                job_card = await page.query_selector('.job_item')
                if not job_card:
                    return "Заказов пока нет", 0.0

                take_button = await job_card.query_selector('a.job_take_link')
                if take_button:
                    await take_button.click()
                    # Тут должна быть логика генерации текста через ИИ и вставки в форму
                    return "Заказ успешно взят в работу!", 150.0 
                
                return "Доступны только тендеры, ждем свободный заказ", 0.0

            except Exception as e:
                logger.error(f"Ошибка: {e}")
                return f"Сбой: {str(e)}", 0.0
            finally:
                await browser.close()
