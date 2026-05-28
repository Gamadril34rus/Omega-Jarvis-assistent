# Фиксируем стабильный дистрибутив Debian (bookworm вместо trixie)
FROM python:3.10-slim-bookworm

WORKDIR /app

# Принудительно устанавливаем ВСЕ системные библиотеки, необходимые для headless-браузеров
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости Python
COPY requirements.txt .

# Обновляем pip и ставим библиотеки
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Скачиваем только бинарник Chromium (зависимости мы уже поставили вручную выше)
RUN playwright install chromium

# Копируем исходный код проекта
COPY jarvis-omega/ .

# Добавляем корневую папку в пути импортов
ENV PYTHONPATH=/app

EXPOSE 10000

CMD uvicorn main:bot --host 0.0.0.0 --port ${PORT:-10000}
