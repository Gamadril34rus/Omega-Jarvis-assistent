FROM python:3.10-slim

WORKDIR /app

# Жестко прописываем переменные окружения прямо в систему
ENV TELEGRAM_BOT_TOKEN="8909414413:AAFa6PLvuP0ZLz7yxZJMJ-d2q601ndFonmk"
ENV TELEGRAM_ADMIN_ID="422343797"

# Дублируем ключ Gemini под всеми именами, которые мог написать Replit
ENV GEMINI_API_KEY="AIzaSyD-L9f3K_mQ8Xz_vP32bN7R5wE1tK9sLpc"
ENV GEMINI_KEY="AIzaSyD-L9f3K_mQ8Xz_vP32bN7R5wE1tK9sLpc"
ENV GOOGLE_API_KEY="AIzaSyD-L9f3K_mQ8Xz_vP32bN7R5wE1tK9sLpc"

# Остальные ключи
ENV DEEPSEEK_API_KEY="sk-d3e7f5a2b1c94e8db3f56a7c8e9f012a"
ENV OPENROUTER_API_KEY="sk-or-v1-7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"
ENV SILICONFLOW_API_KEY="sk-sf-8b9c7d6e5f4a3b2c1d0e9f8a7b6c5d4e"
ENV GROQ_API_KEY="gsk_vM4p9R2X8z7wKq1tY3bN5mP9sL6f1x7vC2dE"
ENV ZHIPU_API_KEY="b4c9e8d7f6a5b4c3.a1b2c3d4e5f6g7h8"

RUN pip install --no-cache-dir fastapi uvicorn aiogram python-dotenv httpx

COPY jarvis-omega/ .

CMD ["python", "main.py"]
