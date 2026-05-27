FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn aiogram python-dotenv httpx

COPY jarvis-omega/ .

CMD ["python", "main.py"]


