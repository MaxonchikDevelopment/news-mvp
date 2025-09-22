# src/database.py
"""Database connection and session management using SQLAlchemy asyncpg."""

# --- Импорты ---
import os
import sys

# Импорты для lifespan
from contextlib import asynccontextmanager

# Импорты для загрузки .env
from dotenv import load_dotenv

# --- Добавлен импорт для FastAPI ---
from fastapi import FastAPI  # <-- Добавь эту строку

# --- Импорты для SQLAlchemy и asyncpg ---
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

from alembic import command
from alembic.config import Config

# --- Загрузка переменных окружения ---
# Явно указываем путь к .env файлу относительно этого файла (src/)
# Это делает загрузку более надежной независимо от того, откуда запускается скрипт
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
# Загружаем файл .env, если он существует
load_dotenv(dotenv_path)

# --- Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Попробуем альтернативный путь или выведем более понятную ошибку
    alt_path = os.path.abspath(dotenv_path)
    print(
        f"Warning: DATABASE_URL not found in environment. Looked in .env at: {alt_path}"
    )
    # Можно бросить исключение, если URL критичен
    # raise ValueError("DATABASE_URL environment variable is not set.")

print(f"✅ .env file loaded from: {dotenv_path}")
print(f"🔍 DATABASE_URL from environment: {'SET' if DATABASE_URL else 'NOT SET'}")
# print(f"🔍 DATABASE_URL value: {DATABASE_URL}") # Осторожно: выводит пароль!

# --- Engine and Session Factory ---
# Проверка на асинхронный драйвер
if DATABASE_URL and not DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise ValueError(
        "Expected DATABASE_URL to start with 'postgresql+asyncpg://' for asyncpg driver."
    )

# Создаем асинхронный движок SQLAlchemy
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Установи True для отладки SQL-запросов
    poolclass=AsyncAdaptedQueuePool,  # Хороший пул по умолчанию для asyncpg
    pool_pre_ping=True,  # Проверяет соединение перед использованием
    pool_recycle=3600,  # Пересоздает соединение каждые 60 минут
)

# Создаем фабрику асинхронных сессий
# Используем expire_on_commit=False, чтобы объекты не истощались после коммита
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# --- Base для моделей ---
# Импортируем базовый класс для моделей после создания engine
# Это помогает избежать циклических импортов в некоторых случаях
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# --- Lifespan для FastAPI ---
# (Убедись, что FastAPI импортирован выше)


@asynccontextmanager
async def lifespan(app: FastAPI):  # <-- Теперь FastAPI определен
    # При запуске приложения
    print("Application startup: Connecting to database and running migrations...")
    # Здесь можно выполнить проверку подключения и запустить миграции Alembic
    # Например, запустить `alembic upgrade head`
    try:
        # Путь к alembic.ini относительно корня проекта
        # Убедись, что путь корректен относительно расположения src/database.py
        alembic_ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        if os.path.exists(alembic_ini_path):
            alembic_cfg = Config(alembic_ini_path)
            # Принудительно запускаем миграции при старте (если нужно)
            # command.upgrade(alembic_cfg, "head")
            # print("Alembic migrations applied.")
            pass  # Пока просто логируем
        else:
            print(
                f"Warning: alembic.ini not found at {alembic_ini_path}. Skipping migration check."
            )
    except Exception as e:
        print(f"Warning: Could not apply migrations on startup: {e}")
    yield
    # При завершении приложения
    print("Application shutdown.")


# --- Dependency для получения сессии ---
# Используем асинхронный генератор для получения сессии
from typing import AsyncGenerator


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency для получения асинхронной сессии БД в FastAPI endpoints.
    Используется с `Depends(get_db_session)`.
    """
    # Проверка, создан ли engine
    if not AsyncSessionFactory:
        raise RuntimeError("Database engine is not configured. Check DATABASE_URL.")

    async with AsyncSessionFactory() as session:
        try:
            # Передаем сессию в эндпоинт
            yield session
        except Exception:
            # В случае ошибки откатываем транзакцию
            await session.rollback()
            raise
        finally:
            # Всегда закрываем сессию
            await session.close()
