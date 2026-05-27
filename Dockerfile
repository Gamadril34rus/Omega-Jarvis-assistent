FROM python:3.10-slim

WORKDIR /app

# Устанавливаем библиотеки
RUN pip install --no-cache-dir fastapi uvicorn aiogram python-dotenv httpx

# Копируем всё содержимое папки jarvis-omega (вместе с твоим файлом .env)
COPY jarvis-omega/ .

# Дополнительно подстрахуемся: если .env лежал уровнем выше, закинем его в корень
RUN cp .env ./ 2>/dev/null || true

CMD ["python", "main.py"]

