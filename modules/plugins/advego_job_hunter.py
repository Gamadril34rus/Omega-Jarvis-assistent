import os
import asyncio
import logging
import random
import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Error as PlaywrightError
from groq import AsyncGroq

try:
    from playwright_stealth.stealth import stealth_async
except ImportError:
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        logging.getLogger("jarvis.plugins.advego_jobs").warning(
            "Модуль stealth_async не обнаружен в системе. Запуск в штатном режиме без дополнительной маскировки."
        )
        async def stealth_async(page):
            pass

logger = logging.getLogger("jarvis.plugins.advego_jobs")
DB_PATH = "advego_hunter.db"


def _parse_llm_json(raw: str) -> dict:
    """
    Отказоустойчивый парсер JSON из ответа LLM.
    Снимает markdown-обёртки вида ```json ... ``` и лишний текст вокруг объекта.
    """
    if not raw:
        return {}
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"[JSON Parser] Не удалось распарсить ответ LLM: {e}. Сырой ответ: {raw[:200]}")
        return {}


class AdvegoJobHunter:
    def __init__(self, router=None):
        self._router = router
        self.cookie_sid = os.getenv("ADVEGO_COOKIE_SID", "")
        self.cookie_token = os.getenv("ADVEGO_COOKIE_TOKEN", "")
        self.proxy_url = os.getenv("PROXY_URL", "")
        self.groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))

        self.screenshot_dir = Path("/app/outputs") if os.path.exists("/app") else Path("./outputs")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_jobs (
                    job_id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    def _is_job_processed(self, job_id: str) -> bool:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("SELECT 1 FROM processed_jobs WHERE job_id = ?", (job_id,))
            return cur.fetchone() is not None

    def _mark_job_status(self, job_id: str, title: str, status: str):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_jobs VALUES (?, ?, ?, ?)",
                (job_id, title, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()

    async def _human_mouse_movement(self, page, target_x: float, target_y: float):
        current_x, current_y = 100.0, 100.0
        steps = random.randint(15, 30)
        for i in range(steps):
            tween = i / steps
            current_x = current_x + (target_x - current_x) * tween + random.uniform(-3, 3)
            current_y = current_y + (target_y - current_y) * tween + random.uniform(-3, 3)
            await page.mouse.move(current_x, current_y)
            await asyncio.sleep(random.uniform(0.01, 0.03))
        await page.mouse.move(target_x, target_y)

    async def _click_cloudflare_checkbox(self, page) -> bool:
        try:
            logger.info("[Stealth-Solver] Поиск защитных фреймов Cloudflare...")
            await page.wait_for_timeout(3000)
            for frame in page.frames:
                if "cloudflare" in frame.url or "turnstile" in frame.url:
                    logger.info("[Stealth-Solver] Фрейм Cloudflare обнаружен. Ищу чекбокс...")
                    checkbox = await frame.query_selector("input[type='checkbox'], #challenge-stage, .cb-i")
                    if checkbox:
                        box = await checkbox.bounding_box()
                        if box:
                            target_x = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
                            target_y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
                            await self._human_mouse_movement(page, target_x, target_y)
                            await page.mouse.down()
                            await asyncio.sleep(random.uniform(0.15, 0.35))
                            await page.mouse.up()
                            logger.info("[Stealth-Solver] Чекбокс Cloudflare обработан. Ожидаю редирект...")
                            await page.wait_for_timeout(5000)
                            return True
            return False
        except (PlaywrightError, Exception) as e:
            logger.error(f"[Stealth-Solver] Не удалось нажать чекбокс: {e}")
            return False

    async def _evaluate_job_with_ai(self, title: str, description: str, addendums: str) -> dict:
        if not os.getenv("GROQ_API_KEY"):
            return {"suitable": False, "reason": "Ключ Groq отсутствует или не инициализирован"}

        prompt = (
            "Ты — автономный ИИ-фрилансер. Оцени, сможешь ли ты выполнить этот заказ на бирже "
            "абсолютно идеально, используя только текстовую генерацию, без риска блокировки аккаунта.\n"
            "Правила оценки:\n"
            "1. Сразу отказывайся (suitable=false), если ТЗ требует: скриншоты, отзывы на внешних картах (Яндекс/Гугл), "
            "скачивание приложений, регистрацию по паспорту, активность в соцсетях (лайки, подписки).\n"
            "2. Одобрение (suitable=true) только для: написания статей, рерайта, постов, SEO-текстов, переводов.\n"
            "3. Обязательно проверь блок дополнений от заказчика на наличие скрытых каверзных условий.\n\n"
            "Ты обязан вернуть ответ СТРОГО в формате чистого JSON без каких-либо Markdown-тегов:\n"
            '{"suitable": true или false, "reason": "краткая причина", "style_hint": "указание по стилю текста"}'
        )

        user_content = f"Название заказа: {title}\nОписание ТЗ: {description}\nДополнения: {addendums}"

        try:
            completion = await self.groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            raw_response = completion.choices[0].message.content or "{}"
            result = _parse_llm_json(raw_response)
            if not result:
                return {"suitable": False, "reason": "Пустой или нераспознанный ответ от LLM"}
            return result
        except Exception as e:
            logger.error(f"[AI Evaluation Error] Не удалось проанализировать заказ через Groq: {e}")
            return {"suitable": False, "reason": f"Ошибка вызова LLM: {e}"}

    async def run(self):
        logger.info("[Hunter-Core] Запуск сессии мониторинга Advego...")

        async with async_playwright() as p:
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
            browser = await p.chromium.launch(headless=True, args=browser_args)

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                proxy={"server": self.proxy_url} if self.proxy_url else None
            )

            if self.cookie_sid or self.cookie_token:
                cookies = []
                if self.cookie_sid:
                    cookies.append({"name": "sid", "value": self.cookie_sid, "domain": ".advego.com", "path": "/"})
                if self.cookie_token:
                    cookies.append({"name": "token", "value": self.cookie_token, "domain": ".advego.com", "path": "/"})
                await context.add_cookies(cookies)

            page = await context.new_page()
            await stealth_async(page)

            try:
                target_url = "https://advego.com/job/find/"
                logger.info(f"[Hunter-Core] Переход на страницу поиска: {target_url}")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)

                await self._click_cloudflare_checkbox(page)

                await page.wait_for_selector(".job-item, .work-block, [id^='job_']", timeout=15000)
                await page.screenshot(path=self.screenshot_dir / "advego_feed.png")

                job_cards = await page.query_selector_all(".job-item, .work-block, [id^='job_']")
                logger.info(f"[Hunter-Core] Найдено {len(job_cards)} карточек на текущей странице.")

                for card in job_cards:
                    try:
                        raw_id = await card.get_attribute("id") or ""
                        job_id = "".join(filter(str.isdigit, raw_id))
                        if not job_id:
                            continue

                        if self._is_job_processed(job_id):
                            continue

                        title_el = await card.query_selector(".job-title, h1, h2, h3, a.job_action")
                        title = await title_el.inner_text() if title_el else "Без названия"
                        title = title.strip().replace("\n", " ")

                        desc_el = await card.query_selector(".job-text, .description, .body")
                        description = await desc_el.inner_text() if desc_el else ""

                        logger.info(f"[Analysis] Проверка заказа #{job_id}: '{title[:45]}...'")

                        evaluation = await self._evaluate_job_with_ai(title, description, "")

                        if evaluation.get("suitable") is True:
                            logger.info(f"[Action] ПОДХОДИТ! Берём в работу. Причина: {evaluation.get('reason')}")

                            take_button = await card.query_selector(
                                "button:has-text('Взять в работу'), .btn-take, .job_action_take"
                            )
                            if take_button:
                                try:
                                    box = await take_button.bounding_box()
                                    if box:
                                        await self._human_mouse_movement(
                                            page,
                                            box["x"] + box["width"] / 2,
                                            box["y"] + box["height"] / 2
                                        )
                                    await take_button.click(timeout=5000)
                                    logger.info(f"[Action] Успешно кликнули на 'Взять в работу' для #{job_id}")
                                    self._mark_job_status(job_id, title, "TAKEN")
                                except PlaywrightError as click_err:
                                    logger.warning(f"[Action] Кнопка исчезла из DOM до клика для #{job_id}: {click_err}")
                                    self._mark_job_status(job_id, title, "CLICK_FAILED")
                            else:
                                logger.warning(f"[Action] Кнопка взятия не найдена для #{job_id} (возможно, тендер)")
                                self._mark_job_status(job_id, title, "SUITABLE_BUT_NO_BUTTON")
                        else:
                            logger.info(f"[Action] Пропуск #{job_id}. Причина: {evaluation.get('reason')}")
                            self._mark_job_status(job_id, title, "SKIPPED")

                    except (PlaywrightError, Exception) as card_err:
                        logger.error(f"Ошибка при парсинге карточки заказа: {card_err}")
                        continue

            except (PlaywrightError, Exception) as e:
                logger.error(f"[Hunter-Core] Критический сбой сессии: {e}")
                try:
                    await page.screenshot(path=self.screenshot_dir / "emergency_crash.png")
                except Exception:
                    pass
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await context.close()
                except Exception:
                    pass
                await browser.close()
                logger.info("[Hunter-Core] Сессия Playwright завершена.")


if __name__ == "__main__":
    hunter = AdvegoJobHunter()
    asyncio.run(hunter.run())