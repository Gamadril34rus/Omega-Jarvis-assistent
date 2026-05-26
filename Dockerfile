# Используем легкий Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код
COPY . .

# Запускаем бота и сервер
CMD ["python", "main.py"]
