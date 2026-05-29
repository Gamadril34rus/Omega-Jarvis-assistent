import os
import asyncio
import logging
import random
import json
from pathlib import Path
from playwright.async_api import async_playwright

logger = logging.getLogger("jarvis.plugins.advego_jobs")

class AdvegoJobHunter:
    def __init__(self, router=None):
        self._router = router
        self.cookie_sid = os.getenv("ADVEGO_COOKIE_SID", "")
        self.cookie_token = os.getenv("ADVEGO_COOKIE_TOKEN", "")
        
        # Настройки прокси (добавь эти переменные в Render, если используешь прокси)
        # Формат: http://username:password@proxy_address:port
        self.proxy_url = os.getenv("PROXY_URL", "") 
        
        self.screenshot_dir = Path("/app/outputs") if os.path.exists("/app") else Path("./outputs")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Путь для сохранения снапшота заказов
        self.snapshot_path = self.screenshot_dir / "snapshot.json"

    async def hunt_and_execute(self) -> tuple[str, float]:
        logger.info("[Advego] Автономный поиск пути пробива... Запуск Playwright.")
        
        if not self.cookie_sid or not self.cookie_token:
            return "Ошибка: Не заданы куки авторизации.", 0.0

        async with async_playwright() as p:
            kiwi_user_agent = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
            
            launch_options = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars"
                ]
            }
            
            if self.proxy_url:
                logger.info("[Advego] Подключение через прокси сервер...")
                launch_options["proxy"] = {"server": self.proxy_url}

            browser = await p.chromium.launch(**launch_options)
            
            context = await browser.new_context(
                user_agent=kiwi_user_agent,
                viewport={"width": 390, "height": 844},
                device_scale_factor=3,
                is_mobile=True,
                has_touch=True,
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                extra_http_headers={
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Sec-Ch-Ua-Mobile": "?1",
                    "Sec-Ch-Ua-Platform": '"Android"'
                }
            )
            
            # Накатываем куки
            await context.add_cookies([
                {"name": "domain_sid", "value": self.cookie_sid, "domain": ".advego.com", "path": "/"},
                {"name": "token", "value": self.cookie_token, "domain": ".advego.com", "path": "/"}
            ])
            
            page = await context.new_page()
            
            # Патч против детекта автоматизации
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ? 
                    Promise.resolve({ state: Notification.permission }) : 
                    originalQuery(parameters)
                );
            """)

            try:
                logger.info("[Advego] Попытка прорыва в ленту заказов...")
                await page.goto("https://advego.com/job/find/", wait_until="domcontentloaded", timeout=30000)
                
                await asyncio.sleep(random.uniform(3.0, 5.0))
                current_url = page.url
                
                if "login" in current_url:
                    logger.warning("[Advego] Пробив не удался: Сервер Advego сбросил сессию на страницу авторизации.")
                    await browser.close()
                    return "Сессия отклонена сервером (требуется обновить куки).", 0.0

                title = await page.title()
                if "Cloudflare" in title or "Just a moment" in title:
                    logger.warning("[Advego] Путь заблокирован Cloudflare.")
                    await browser.close()
                    return "Блокировка Cloudflare.", 0.0

                logger.info("[Advego] Ура! Прорыв успешен. Начинаю сбор элементов...")
                
                # --- БЛОК СБОРА ДАННЫХ (БЫСТРЫЙ И БЕЗОПАСНЫЙ) ---
                # Собираем все ссылки, содержащие переходы на заказы
                job_links = await page.query_selector_all("a[href*='/job/']")
                
                parsed_jobs = []
                seen_ids = set()
                
                for el in job_links:
                    if len(parsed_jobs) >= 20:
                        break
                    try:
                        href = await el.get_attribute("href") or ""
                        text = await el.inner_text()
                        text = text.strip()
                        
                        if not text or len(text) < 10: 
                            continue # Пропускаем пустые ссылки или короткие кнопки типа "Подробнее"
                            
                        # Выдергиваем ID из ссылки типа /job/view/123456/ или из параметров
                        parts = [p for p in href.split("/") if p]
                        job_id = "unknown"
                        for i, part in enumerate(parts):
                            if part == "view" and i + 1 < len(parts):
                                job_id = parts[i + 1]
                                break
                        
                        if job_id in seen_ids:
                            continue
                            
                        seen_ids.add(job_id)
                        
                        # Косметически урезаем заголовок, если он слишком длинный
                        clean_title = " ".join(text.split())
                        if len(clean_title) > 80:
                            clean_title = clean_title[:77] + "..."
                            
                        parsed_jobs.append({
                            "id": job_id,
                            "title": clean_title,
                            "price": "Парсинг цены отключен"
                        })
                    except Exception:
                        continue
                
                # Сохраняем результат в файл snapshot.json
                self.snapshot_path.write_text(json.dumps(parsed_jobs, ensure_ascii=False, indent=2))
                logger.info(f"[Advego] Сбор завершен. Найдено и сохранено {len(parsed_jobs)} уникальных заказов.")
                
                await browser.close()
                return f"Успешный прорыв! Собрано элементов: {len(parsed_jobs)}", 0.0

            except Exception as e:
                logger.error(f"[Advego] Ошибка при парсинге: {e}")
                await browser.close()
                return f"Сбой метода: {e}", 0.0
