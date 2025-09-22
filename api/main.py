# api/main.py
"""Main FastAPI application entry point."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # <-- Добавь эту строку

from api.routes import router as api_router
from src.database import lifespan  # Добавлен импорт

# Импортируем lifespan для Alembic (опционально, но рекомендуется)
# from src.database import lifespan


# Создаем экземпляр FastAPI приложения с lifespan
app = FastAPI(title="Smart News MVP API", version="0.1.0", lifespan=lifespan)

# --- Добавь настройку CORS ---
# Настройки для разработки (разрешает всё)
# В production нужно быть более строгим
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],  # Позволяет запросы с любого источника (file://, http://localhost:3000 и т.д.)
    allow_credentials=True,
    allow_methods=["*"],  # Позволяет любые методы (GET, POST, OPTIONS и т.д.)
    allow_headers=["*"],  # Позволяет любые заголовки (включая Authorization)
)
# Настройка CORS (если будет фронтенд на другом порту)
# origins = [
#     "http://localhost:3000", # Пример для React/Vue
#     # Другие origins
# ]
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# Подключаем (включаем) маршруты из api_router к основному приложению
# Все пути в api_router теперь будут начинаться с /api/v1
app.include_router(api_router, prefix="/api/v1")


# Корневой эндпоинт для проверки работы API
@app.get("/")
async def read_root():
    return {"message": "Welcome to the Smart News MVP API"}


# Для запуска сервера в терминале используется команда:
# uvicorn api.main:app --reload
