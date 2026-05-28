import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger("jarvis.plugins.advego_jobs")

class AdvegoJobHunter:
    def __init__(self, router):
        self._router = router
        # Данные авторизации
        self._login = "zmey1341@mail.ru"
        self._password = "Samsung777+"

    async def hunt_and_execute(self):
        async with async_playwright() as p:
            # Запуск Chromium с флагами для стабильной работы внутри Docker-контейнера
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                    "--no-zygote"
                ]
            )
            
            # Маскируемся под обычный браузер, чтобы избежать мгновенного бана
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()

            try:
                logger.info("Переход на страницу авторизации Advego...")
                # 1. Авторизация
                await page.goto("https://advego.com/login/", timeout=60000)
                
                # Добавляем :visible, чтобы Playwright не цеплял скрытую форму регистрации
                await page.fill('input[name="email"]:visible', self._login)
                await page.fill('input[name="password"]:visible', self._password)
                
                # Кликаем именно по видимой кнопке отправки
                await page.click('button[type="submit"]:visible')
                
                logger.info("Ожидание завершения авторизации...")
                # Вместо жесткого sleep(5) надежнее подождать, пока сменится URL или закроется форма
                try:
                    await page.wait_for_url("https://advego.com/", timeout=15000)
                except Exception:
                    # Если редиректнуло в другое место или остался старый URL, делаем паузу как запасной вариант
                    await asyncio.sleep(5) 

                logger.info("Переход на страницу поиска заказов...")
                # 2. Поиск доступных заказов (Копирайтинг и Рерайт)
                await page.goto("https://advego.com/job/find/?job_type=1&job_type=2", timeout=60000)
                
                # Ждем появления хотя бы одной карточки заказа (максимум 10 секунд)
                try:
                    await page.wait_for_selector('.job_item', timeout=10000)
                except Exception:
                    logger.info("На странице нет доступных карточек заказов.")
                    return "Заказов пока нет", 0.0
                
                # Ищем первую карточку
                job_card = await page.query_selector('.job_item')
                if not job_card:
                    return "Заказов пока нет", 0.0

                # Ищем кнопку "Взять в работу"
                take_button = await job_card.query_selector('a.job_take_link')
                if take_button:
                    await take_button.click()
                    logger.info("Кнопка 'Взять в работу' успешно нажата!")
                    # Тут будет логика генерации текста через Gemini и отправки формы
                    return "Заказ успешно взят в работу!", 150.0 
                
                return "Доступны только тендеры, ждем свободный заказ", 0.0

            except Exception as e:
                logger.error(f"Ошибка в работе AdvegoJobHunter: {e}", exc_info=True)
                return f"Сбой: {str(e)}", 0.0
            finally:
                # Обязательно закрываем контекст и браузер, чтобы не плодить зомби-процессы
                await context.close()
                await browser.close()
