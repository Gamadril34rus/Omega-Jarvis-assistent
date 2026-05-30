import os
import asyncio
import logging
import sqlite3
import random
import html
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Error as PlaywrightError
from groq import AsyncGroq
from aiogram import Router

try:
    from playwright_stealth.stealth import stealth_async
except ImportError:
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        logging.getLogger("jarvis.plugins.network_empire").warning(
            "Модуль stealth_async не обнаружен в системе для NetworkEmpire. Запуск без дополнительной маскировки."
        )
        async def stealth_async(page):
            pass

logger = logging.getLogger("jarvis.plugins.network_empire")
DB_PATH = "network_empire.db"

router = Router()


def _sanitize_html(text: str) -> str:
    """
    Очищает текст перед отправкой в Telegram с parse_mode='HTML'.
    Экранирует все спецсимволы HTML за пределами допустимых тегов <b> и <i>.
    Стратегия: извлекаем теги <b>/<i>, экранируем всё остальное, собираем обратно.
    """
    if not text:
        return ""
    allowed_tags_pattern = re.compile(r'(</?(?:b|i)>)', re.IGNORECASE)
    parts = allowed_tags_pattern.split(text)
    result = []
    for part in parts:
        if allowed_tags_pattern.fullmatch(part):
            result.append(part.lower())
        else:
            result.append(html.escape(part))
    return "".join(result)


import re


class NetworkEmpireManager:
    def __init__(self, bot=None, groq_client=None):
        self.bot = bot
        self.groq_client = groq_client or AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))
        self.proxy_url = os.getenv("PROXY_URL", "")

        self.channels = {
            "auto_tools": os.getenv("CH_AUTO_TOOLS", ""),
            "fishing": os.getenv("CH_FISHING", ""),
            "electronics": os.getenv("CH_ELECTRONICS", ""),
            "android_mods": os.getenv("CH_ANDROID_MODS", "")
        }

        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS published_deals (
                    deal_id TEXT PRIMARY KEY,
                    title TEXT,
                    category TEXT,
                    published_at TEXT
                )
            """)
            conn.commit()

    def _is_deal_published(self, deal_id: str) -> bool:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("SELECT 1 FROM published_deals WHERE deal_id = ?", (deal_id,))
            return cur.fetchone() is not None

    def _mark_deal_published(self, deal_id: str, title: str, category: str):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO published_deals VALUES (?, ?, ?, ?)",
                (deal_id, title, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()

    async def generate_post_text(self, title: str, description: str, category: str) -> str:
        """Генерация уникального HTML-контента под ЦА каждого канала через Groq."""
        if not os.getenv("GROQ_API_KEY"):
            return f"🔥 Отличная скидка: <b>{html.escape(title)}</b>\n\n{html.escape(description)}"

        prompts = {
            "auto_tools": (
                "Ты — опытный автомеханик и эксперт по подбору инструмента. "
                "Напиши брутальный, экспертный и цепляющий пост для мужиков про эту скидку. "
                "Используй уместный технический сленг."
            ),
            "fishing": (
                "Ты — заядлый рыбак, знающий толк в ловле хищника на Волге и Ахтубе. "
                "Напиши душевный, но продающий пост о рыболовном снаряжении. "
                "Объясни практическую пользу на водоёме."
            ),
            "electronics": (
                "Ты — молодой и дерзкий техноблогер. Напиши хайповый, динамичный пост про гаджеты/девайсы "
                "с использованием современного сленга, эмодзи и явным упором на выгоду."
            ),
            "android_mods": (
                "Ты — гик и разработчик мобильного софта. Опиши преимущества этого приложения или девайса, "
                "разложи по полочкам скрытые фичи доступным языком."
            ),
        }

        system_prompt = prompts.get(
            category,
            "Ты — креативный копирайтер. Напиши качественный рекламный пост для Telegram-каналов."
        )
        system_prompt += (
            "\nПиши лаконично, структурировано, используй списки и эмодзи. "
            "Для форматирования используй ИСКЛЮЧИТЕЛЬНО HTML-теги: <b>текст</b> для жирного и <i>текст</i> для курсива. "
            "ЗАПРЕЩЕНО использовать символы *, _, [, ] и любые другие Markdown-конструкции. "
            "Не используй теги за пределами <b> и <i>."
        )

        try:
            completion = await self.groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Товар: {title}\nОписание/Инфо: {description}"}
                ],
                temperature=0.7
            )
            raw_text = completion.choices[0].message.content or title
            return _sanitize_html(raw_text)
        except Exception as e:
            logger.error(f"[Groq Empire] Ошибка генерации текста через LLM: {e}")
            return f"🛍 <b>{html.escape(title)}</b>\n\n{html.escape(description)}"

    async def scrape_pepper_deals(self):
        """Парсинг новых карточек товаров с Pepper.ru через асинхронный Playwright."""
        deals = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                proxy={"server": self.proxy_url} if self.proxy_url else None
            )
            page = await context.new_page()
            await stealth_async(page)

            try:
                logger.info("[Empire-Parser] Подключение к Pepper.ru...")
                await page.goto("https://www.pepper.ru/new", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)

                cards = await page.query_selector_all("article.thread")
                for card in cards:
                    try:
                        id_attr = await card.get_attribute("id") or ""
                        deal_id = "".join(filter(str.isdigit, id_attr))
                        if not deal_id:
                            continue

                        title_el = await card.query_selector("strong.thread-title a")
                        if not title_el:
                            continue
                        title = (await title_el.inner_text()).strip()
                        link = await title_el.get_attribute("href") or ""

                        title_lower = title.lower()
                        if any(x in title_lower for x in ["набор", "ключ", "авто", "масло", "шина", "инструмент", "головки"]):
                            category = "auto_tools"
                        elif any(x in title_lower for x in ["спиннинг", "удочка", "воблер", "леска", "крючок", "рыбалка", "катушка"]):
                            category = "fishing"
                        elif any(x in title_lower for x in ["смартфон", "наушники", "xiaomi", "зарядка", "powerbank", "мышь", "клавиатура"]):
                            category = "electronics"
                        elif any(x in title_lower for x in ["vpn", "подписка", "курс", "программа", "софт", "приложение", "активация"]):
                            category = "android_mods"
                        else:
                            category = "electronics"

                        deals.append({
                            "id": deal_id,
                            "title": title,
                            "link": f"https://www.pepper.ru{link}" if link.startswith("/") else link,
                            "category": category
                        })
                    except (PlaywrightError, Exception) as card_err:
                        logger.error(f"Не удалось распарсить элемент ленты: {card_err}")
                        continue

            except (PlaywrightError, Exception) as e:
                logger.error(f"[Empire-Parser] Ошибка при чтении веб-страницы: {e}")
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

        return deals

    async def auto_post_cycle(self):
        """Основной цикл мониторинга, уникализации контента и публикации."""
        logger.info("[Empire-Core] Запуск планового цикла проверки сетей...")
        deals = await self.scrape_pepper_deals()

        for deal in deals:
            if self._is_deal_published(deal["id"]):
                continue

            category = deal["category"]
            channel_id = self.channels.get(category)

            if not channel_id:
                logger.warning(f"[Empire-Core] ID канала для категории '{category}' не задан. Пропуск.")
                continue

            logger.info(f"[Empire-Core] Публикация нового оффера {deal['id']} в категорию {category}...")

            post_text = await self.generate_post_text(
                deal["title"],
                f"Ссылка на скидку: {deal['link']}",
                category
            )

            if self.bot:
                try:
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=post_text,
                        parse_mode="HTML"
                    )
                    logger.info(f"[Empire-Core] Пост успешно отправлен в Telegram [{category}].")
                except Exception as tg_err:
                    logger.error(
                        f"[Empire-Core] Ошибка публикации в канал '{category}' (id={channel_id}): {tg_err}. "
                        "Продолжаю обработку следующих офферов."
                    )
                    continue
            else:
                logger.info(f"[Empire-Core] (bot=None) Пост для [{category}]:\n{post_text}\n" + "=" * 50)

            self._mark_deal_published(deal["id"], deal["title"], category)
            await asyncio.sleep(random.randint(15, 35))

    async def initial_bulk_fill(self):
        """Первичный прогрев сетки каналов при развертывании."""
        logger.info("[Empire-Core] Выполняется стартовое наполнение каналов контентом (Bulk Fill)...")
        for _ in range(2):
            await self.auto_post_cycle()
            await asyncio.sleep(10)


if __name__ == "__main__":
    manager = NetworkEmpireManager()
    asyncio.run(manager.initial_bulk_fill())