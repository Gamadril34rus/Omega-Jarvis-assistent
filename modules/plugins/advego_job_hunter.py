import os
import asyncio
import logging
import random
import json
from pathlib import Path
from playwright.async_api import async_playwright
from groq import AsyncGroq

# --- АВТОНОМНЫЙ ИСПРАВЛЕННЫЙ ИМПОРТ STEALTH-ПАКЕТА ---
try:
    # Рабочий путь для сборки Linux (на Render)
    from playwright_stealth.stealth import stealth_async
except ImportError:
    try:
        # Классический путь для Windows
        from playwright_stealth import stealth_async
    except ImportError:
        # Резервный вариант: если библиотека встала криво, бот не упадет, а продолжит работу
        logging.getLogger("jarvis.plugins.advego_jobs").warning(
            "Модуль stealth_async не обнаружен в системе. Запуск в штатном режиме."
        )
        async def stealth_async(page):
            pass
# ----------------------------------------------------

logger = logging.getLogger("jarvis.plugins.advego_jobs")

class AdvegoJobHunter:
    def __init__(self, router=None):
        self._router = router
        self.cookie_sid = os.getenv("ADVEGO_COOKIE_SID", "")
        self.cookie_token = os.getenv("ADVEGO_COOKIE_TOKEN", "")
        self.proxy_url = os.getenv("PROXY_URL", "") 
        self.groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))
        
        self.screenshot_dir = Path("/app/outputs") if os.path.exists("/app") else Path("./outputs")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _click_cloudflare_checkbox(self, page) -> bool:
        """Бесплатный автопробив: поиск и клик по чекбоксу Cloudflare Turnstile внутри фрейма"""
        try:
            logger.info("[Stealth-Solver] Поиск защитных фреймов Cloudflare...")
            # Ждем появления фрейма капчи
            await page.wait_for_timeout(2000)
            
            for frame in page.frames:
                if "cloudflare" in frame.url or "turnstile" in frame.url:
                    logger.info("[Stealth-Solver] Фрейм Cloudflare обнаружен. Ищу чекбокс...")
                    checkbox = await frame.query_selector("input[type='checkbox'], #challenge-stage, .cb-i")
                    if checkbox:
                        # Получаем координаты центра чекбокса
                        box = await checkbox.bounding_box()
                        if box:
                            # Имитируем реальное человеческое движение мыши к объекту
                            await page.mouse.move(
                                box["x"] + box["width"] / 2 + random.uniform(-2, 2),
                                box["y"] + box["height"] / 2 + random.uniform(-2, 2)
                            )
                            await page.mouse.down()
                            await asyncio.sleep(random.uniform(0.1, 0.3))
                            await page.mouse.up()
                            logger.info("[Stealth-Solver] Чекбокс Cloudflare успешно нажат без сторонних сервисов!")
                            await page.wait_for_timeout(4000)
                            return True
            return False
        except Exception as e:
            logger.error(f"[Stealth-Solver] Не удалось нажать чекбокс: {e}")
            return False

    async def _evaluate_job_with_ai(self, title: str, description: str) -> bool:
        """Анализ ТЗ"""
        prompt = (
            "Определи, может ли ИИ выполнить заказ автономно только текстом. "
            "ДА - статьи, отзывы, рерайт, переводы. "
            "НЕТ - скачивания, реги, соцсети, лайки, фото. "
            "Отвечай ТОЛЬКО 'YES' или 'NO'.\n"
            f"Заголовок: {title}\nТЗ: {description}"
        )
        try:
            completion = await self.groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=5
            )
            return "YES" in completion.choices[0].message.content.strip().upper()
        except Exception:
            return False

    async def _generate_human_work(self, description: str) -> str:
        """Генерация текста"""
        system_prompt = (
            "Ты опытный фрилансер. Выполни ТЗ. Пиши живо, разговорно, без нейро-штампов, "
            "соблюдай ключи. Сразу выдавай готовый текст работы без приветствий и лишней воды."
        )
        try:
            completion = await self.groq_client.chat.completions.create(
                model="llama3-70b-8192", 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Выполни это ТЗ: {description}"}
                ],
                temperature=0.7,
            )
            return completion.choices[0].message.content.strip()
        except Exception:
            return "Сбой генерации текста."

    async def hunt_and_execute(self) -> tuple[str, float]:
        logger.info("[Advego] Запуск Бесплатного Автономного Агента (Режим: Усиленный Стелс)...")
        
        if not self.cookie_sid or not self.cookie_token:
            return "Ошибка: Не заданы куки.", 0.0

        async with async_playwright() as p:
            launch_options = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1920,1080"
                ]
            }
            if self.proxy_url:
                launch_options["proxy"] = {"server": self.proxy_url}

            browser = await p.chromium.launch(**launch_options)
            
            # Формируем чистый контекст обычного ПК
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="ru-RU",
                timezone_id="Europe/Moscow"
            )
            
            page = await context.new_page()
            
            # Инжектируем профессиональный стелс-пакет (скрывает автоматизацию напрочь)
            await stealth_async(page)
            
            # Накатываем куки авторизации
            await context.add_cookies([
                {"name": "domain_sid", "value": self.cookie_sid, "domain": ".advego.com", "path": "/"},
                {"name": "token", "value": self.cookie_token, "domain": ".advego.com", "path": "/"}
            ])

            try:
                # 1. Заходим в ленту заказов
                await page.goto("https://advego.com/job/find/", wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)

                # Проверяем, вылезла ли блокировка / чекбокс
                title = await page.title()
                if "Just a moment" in title or "Cloudflare" in title:
                    logger.warning("[Advego] Зафиксирован барьер Cloudflare. Включаю бесплатный кликер...")
                    solved = await self._click_cloudflare_checkbox(page)
                    if not solved:
                        await browser.close()
                        return "Капча заблокировала проход. Стелс не справился.", 0.0

                if "login" in page.url:
                    await browser.close()
                    return "Сессия слетела (неверные куки).", 0.0

                # Ищем доступные задачи
                job_links_elements = await page.query_selector_all("a[href*='/job/view/']")
                job_urls = []
                for el in job_links_elements:
                    href = await el.get_attribute("href")
                    if href and href not in job_urls:
                        job_urls.append(f"https://advego.com{href}" if href.startswith("/") else href)

                if not job_urls:
                    await browser.close()
                    return "Заказы не найдены в ленте.", 0.0

                # 2. Быстрый прогон по карточкам
                for job_url in job_urls[:5]:
                    await page.goto(job_url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)

                    title_el = await page.query_selector("h1")
                    desc_el = await page.query_selector(".task-description, div[itemprop='description']") 
                    
                    if not title_el or not desc_el:
                        continue

                    title = await title_el.inner_text()
                    description = await desc_el.inner_text()

                    # Оценка пригодности заказа через ИИ
                    can_do = await self._evaluate_job_with_ai(title, description)
                    if not can_do:
                        continue

                    logger.info(f"[Advego] Беру в работу: {title[:40]}")

                    # Клик "Взять в работу"
                    take_btn = await page.query_selector("button:has-text('Взять в работу'), a:has-text('Взять в работу')")
                    if take_btn:
                        await take_btn.click()
                        await page.wait_for_timeout(1000)
                        
                        confirm_btn = await page.query_selector("button:has-text('Подтвердить'), button.btn-success")
                        if confirm_btn:
                            await confirm_btn.click()

                    # Генерация контента в фоне
                    result_text = await self._generate_human_work(description)
                    if result_text == "Сбой генерации текста.":
                        continue

                    # Выдерживаем паузу безопасности (15 сек), чтобы не спалиться перед антифродом Advego
                    await page.wait_for_timeout(15000)

                    # Переход к форме сдачи
                    execute_btn = await page.query_selector("a:has-text('Выполнить'), button:has-text('Отправить работу')")
                    if execute_btn:
                        await execute_btn.click()
                        await page.wait_for_timeout(1500)

                    textarea = await page.query_selector("textarea[name='job_text'], textarea.report-text")
                    if textarea:
                        logger.info("[Advego] Скоростной ввод готового текста...")
                        # Печатаем быстро (задержка 5-12 мс), имитируя бешеную скорость профи
                        await textarea.type(result_text, delay=random.randint(5, 12)) 
                        await page.wait_for_timeout(1000)

                        submit_btn = await page.query_selector("button[type='submit']:has-text('Отправить')")
                        if submit_btn:
                            await submit_btn.click()
                            logger.info("[Advego] Работа успешно сдана заказчику без копейки затрат на капчу!")
                            await browser.close()
                            return f"Успех! Работа выполнена: {title[:30]}...", 0.0

                await browser.close()
                return "В текущей ленте нет подходящих задач для ИИ.", 0.0

            except Exception as e:
                logger.error(f"[Advego Ошибка]: {e}", exc_info=True)
                await browser.close()
                return f"Сбой системы: {e}", 0.0
