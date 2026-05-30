FROM python:3.10-slim-bookworm

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libgtk-3-0 libgbm1 libasound2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libpango-1.0-0 libcairo2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Установка браузера
RUN playwright install chromium

# Копируем ВЕСЬ код в корень /app
COPY . .

# Указываем, что Python должен смотреть в корень
ENV PYTHONPATH=/app

CMD ["python", "main.py"]
