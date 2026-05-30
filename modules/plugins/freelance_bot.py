import logging
import httpx
import xml.etree.ElementTree as ET

logger = logging.getLogger("jarvis.modules.plugins.freelance")

class FreelanceAutomator:
    def __init__(self, router):
        self._router = router

    async def hunt_and_solve(self) -> tuple[str, float]:
        # Парсинг открытой RSS-ленты удаленных заказов (на примере Хабр Фриланса)
        rss_url = "https://freelance.habr.com/tasks.rss"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(rss_url)
            if resp.status_code != 200:
                return "Не удалось получить RSS-ленту с биржи фриланса", 0.0

        root = ET.fromstring(resp.content)
        tasks = root.findall(".//item")
        
        if not tasks:
            return "Новых доступных задач на бирже не найдено.", 0.0

        # Берем верхнюю (самую свежую) задачу из ленты
        latest_task = tasks[0]
        title = latest_task.find("title").text
        description = latest_task.find("description").text
        link = latest_task.find("link").text

        # Проверяем, подходит ли тематика под возможности Jarvis
        keywords = ["написать", "текст", "python", "копирайт", "статья", "бот", "автоматизация"]
        if not any(kw in title.lower() or kw in description.lower() for kw in keywords):
            return f"Задача '{title}' пропущена (не соответствует стеку ИИ)", 0.0

        # Формируем отклик на задание
        prompt = (
            f"Ты — автономный фрилансер Jarvis. Сгенерируй профессиональный и убедительный отклик на заказ.\n"
            f"Название: {title}\n"
            f"Описание задачи: {description}\n\n"
            f"Напиши клиенту, почему мы легко справимся с проектом, укажи краткий план действий и покажи готовность начать прямо сейчас."
        )
        
        messages = [{"role": "user", "content": prompt}]
        proposal = await self._router.complete(messages)
        
        # Симулируем потенциальную ценность выполнения микрозадачи в долларах
        potential_revenue = 4.50 
        
        return f"Сгенерирован отклик на заказ '{title}' (Ссылка: {link}). Текст отклика: {proposal[:80]}...", potential_revenue
