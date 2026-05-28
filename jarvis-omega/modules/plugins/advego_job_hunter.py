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
        # Динамически определяем путь к папке static для сохранения скриншотов
        self._static_dir = Path(__file__).resolve().parents[2] / "static"

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
            
            # Маскируемся под обычный браузер
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()

            try:
                logger.info("Переход на страницу авторизации Advego...")
                await page.goto("https://advego.com/login/", timeout=60000)
                
                # Ожидаем, пока прекратится активный сетевой обмен
                await page.wait_for_load_state("networkidle")
                
                # Ждем появления формы авторизации
                try:
                    await page.wait_for_selector('form[action*="login"]', timeout=10000)
                except Exception:
                    logger.warning("[Advego] Форма входа не найдена по селектору формы. Проверяем вкладку 'Вход'...")
                    login_tab = await page.query_selector('text="Вход"')
                    if login_tab and await login_tab.is_visible():
                        await login_tab.click()
                        await asyncio.sleep(2)

                # Локализуем конкретную форму авторизации, чтобы не цеплять скрытые инпуты регистрации
                login_form = page.locator('form[action*="login"], #host_login_form, .blocks-container').first
                
                # Ищем и заполняем поле для логина внутри этой формы
                login_input = login_form.locator('input[name="login"], input[name="email"]').first
                await login_input.click()
                await login_input.fill(self._login)
                await asyncio.sleep(0.5)
                
                # Ищем и заполняем поле пароля строго внутри этой же формы
                password_input = login_form.locator('input[name="password"]').first
                await password_input.click()
                await password_input.fill(self._password)
                await asyncio.sleep(0.5)
                
                # Кликаем по кнопке отправки внутри формы
                submit_button = login_form.locator('button[type="submit"], input[type="submit"], .btn_orange').first
                await submit_button.click()
                
                logger.info("Ожидание завершения авторизации...")
                try:
                    await page.wait_for_url("https://advego.com/", timeout=15000)
                except Exception:
                    await asyncio.sleep(5) 

                logger.info("Переход на страницу поиска заказов...")
                await page.goto("https://advego.com/job/find/?job_type=1&job_type=2", timeout=60000)
                
                try:
                    await page.wait_for_selector('.job_item', timeout=10000)
                except Exception:
                    logger.info("На странице нет доступных карточек заказов.")
                    return "Заказов пока нет", 0.0
                
                job_card = await page.query_selector('.job_item')
                if not job_card:
                    return "Заказов пока нет", 0.0

                # Ищем кнопку "Взять в работу"
                take_button = await job_card.query_selector('a.job_take_link')
                if take_button:
                    await take_button.click()
                    logger.info("Кнопка 'Взять в работу' успешно нажата!")
                    return "Заказ успешно взят в работу!", 150.0 
                
                return "Доступны только тендеры, ждем свободный заказ", 0.0

            except Exception as e:
                logger.error(f"Ошибка в работе AdvegoJobHunter: {e}", exc_info=True)
                
                # Сохраняем скриншот страницы при любой непредвиденной ошибке
                if self._static_dir.exists():
                    screenshot_path = self._static_dir / "advego_error.png"
                    try:
                        await page.screenshot(path=str(screenshot_path))
                        logger.info(f"[Advego] Скриншот страницы ошибки сохранен: {screenshot_path}")
                    except Exception as screenshot_err:
                        logger.error(f"Не удалось сохранить скриншот: {screenshot_err}")
                
                return f"Сбой: {str(e)}", 0.0
            finally:
                # Надежное закрытие сессии браузера
                await context.close()
                await browser.close()
