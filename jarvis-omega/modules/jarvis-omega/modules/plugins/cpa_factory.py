import logging
import os
import httpx

logger = logging.getLogger("jarvis.modules.plugins.cpa")

class CPAContentFactory:
    def __init__(self, router):
        self._router = router
        # Подтягиваем токен бота и ID админа/канала из переменных окружения Render
        self._bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        # Используем существующий TELEGRAM_ADMIN_ID как дефолтный чат для тестов постинга
        self._channel_id = os.getenv("TELEGRAM_ADMIN_ID", "")

    async def generate_and_post(self) -> str:
        if not self._bot_token or not self._channel_id:
            raise ValueError("Telegram credentials are missing in environment variables.")

        # Товарный оффер (в будущем сюда можно прикрутить парсинг реальной CPA-ленты)
        product_title = "Умный автомобильный компрессор для шин (аккумуляторный)"
        ref_link = "https://ozon.ru/referral_placeholder_link" 
        
        prompt = (
            f"Напиши короткий, нативный и вовлекающий пост для Telegram-канала с обзором на товар: '{product_title}'. "
            f"Используй эмодзи, нажми на боли водителей (спущенное колесо ночью, мороз, неудобные ручные насосы) и сделай призыв к покупке. "
            f"В конце поста обязательно размести ссылку: {ref_link}"
        )
        
        messages = [{"role": "user", "content": prompt}]
        post_content = await self._router.complete(messages)
        
        # Отправка в Telegram
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._channel_id,
            "text": post_content,
            "parse_mode": "HTML"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Telegram API Error: {resp.text}")
                
        return f"Успешно опубликован CPA-пост про '{product_title}' в чат/канал {self._channel_id}"
