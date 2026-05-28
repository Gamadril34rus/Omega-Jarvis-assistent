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
                
                # Проверяем наличие основной формы авторизации
                try:
                    await page.wait_for_selector('#host_login_form, form[action*="login"]', timeout=15000)
                except Exception:
                    logger.warning("[Advego] Основная форма не найдена, пробуем принудительно открыть вкладку 'Вход'")
                    # Нажимаем на вкладку "Вход" через JS на случай, если она перекрыта анимацией
                    await page.evaluate("() => { const tabs = document.querySelectorAll('.tabs_list li'); tabs.forEach(t => { if(t.innerText.includes('Вход')) t.click(); }); }")
                    await asyncio.sleep(2)

                logger.info("Заполнение данных авторизации...")

                # Точные селекторы по ID и атрибутам для логина
                email_field = page.locator('#login_email, input[name="login"], input[name="email"]').first
                await email_field.wait_for(state="visible", timeout=15000)
                await email_field.fill(self._login)
                
                # Точные селекторы по ID и атрибутам для пароля
                password_field = page.locator('#login_password, input[name="password"]').first
                await password_field.wait_for(state="visible", timeout=15000)
                await password_field.fill(self._password)
                
                await asyncio.sleep(1)
                
                # Кнопка отправки формы входа
                submit_btn = page.locator('#host_login_form button[type="submit"], .btn_orange, button:has-text("Войти")').first
                await submit_btn.click()
                
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
                # Надежное закрытие сессии браузера без вызова сторонних атрибутов
                await context.close()
                await browser.close()
