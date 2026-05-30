import os
import asyncio
import logging
import random
import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from groq import AsyncGroq

# --- АВТОНОМНЫЙ ИСПРАВЛЕННЫЙ ИМПОРТ STEALTH-ПАКЕТА ---
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
# ----------------------------------------------------

logger = logging.getLogger("jarvis.plugins.advego_jobs")
DB_PATH = "advego_hunter.db"

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
        """Инициализация базы данных для отслеживания обработанных задач"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_jobs (
                job_id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _is_job_processed(self, job_id: str) -> bool:
        """Проверяет, обрабатывался ли этот заказ ранее"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM processed_jobs WHERE job_id = ?", (job_id,))
        res = cur.fetchone()
        conn.close()
        return res is not None

    def _mark_job_status(self, job_id: str, title: str, status: str):
        """Сохраняет статус заказа в БД, чтобы не спамить проверками"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO processed_jobs VALUES (?, ?, ?, ?)",
            (job_id, title, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()

    async def _human_mouse_movement(self, page, target_x: float, target_y: float):
        """Генерация реалистичной траектории движения мыши с шумом вместо прямой линии"""
        current_x, current_y = 100.0, 100.0  # Начальная условная точка
        steps = random.randint(15, 30)
        
        for i in range(steps):
            tween = i / steps
            # Линейное смещение с наложением синусоидального шума
            current_x = current_x + (target_x - current_x) * tween + random.uniform(-3, 3)
            current_y = current_y + (target_y - current_y) * tween + random.uniform(-3, 3)
            await page.mouse.move(current_x, current_y)
            await asyncio.sleep(random.uniform(0.01, 0.03))
            
        await page.mouse.move(target_x, target_y)

    async def _click_cloudflare_checkbox(self, page) -> bool:
        """Поиск и эмуляция клика по чекбоксу Cloudflare Turnstile внутри фреймов"""
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
        except Exception as e:
            logger.error(f"[Stealth-Solver] Не удалось нажать чекбокс: {e}")
            return False

    async def _evaluate_job_with_ai(self, title: str, description: str, addendums: str) -> dict:
        """Глубокий когнитивный анализ ТЗ и скрытых дополнений заказчика"""
        if not self.groq_client:
            return {"suitable": False, "reason": "Ключ Groq отсутствует"}

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

        try:
            completion = await self.groq
