FROM python:3.10-slim

WORKDIR /app

# Устанавливаем библиотеки
RUN pip install --no-cache-dir fastapi uvicorn aiogram python-dotenv httpx

# Копируем код проекта
COPY jarvis-omega/ .

# ХАК: Копируем секретный файл .env из папки Render прямо в корень приложения
RUN cp /etc/secrets/.env ./.env 2>/dev/null || true

CMD ["python", "main.py"]
