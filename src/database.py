# src/database.py
"""Database connection and session management using SQLAlchemy asyncpg."""

import os
import sys

# --- Исправленный импорт и загрузка .env ---
from dotenv import load_dotenv

# Явно указываем путь к .env файлу относительно этого файла (src/)
# Это делает загрузку более надежной независимо от того, откуда запускается скрипт
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
# Альтернатива: можно указать абсолютный путь, если относительный не работает
# dotenv_path = "/Users/admin/Desktop/Maximchik/news-mvp/.env"

# Проверяем, существует ли файл .env
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"✅ .env file loaded from: {dotenv_path}")  # Для отладки
else:
    print(f"⚠️ .env file NOT FOUND at: {dotenv_path}")  # Для отладки
    # Пытаемся загрузить из текущей директории (поведение по умолчанию)
    load_dotenv()
    print("🔄 Trying to load .env from current working directory...")  # Для отладки

# --- Конец исправленной загрузки .env ---

DATABASE_URL = os.getenv("DATABASE_URL")
print(
    f"🔍 DATABASE_URL from environment: {'SET' if DATABASE_URL else 'NOT SET'}"
)  # Для отладки

if not DATABASE_URL:
    # ВАЖНО: Не выбрасываем исключение сразу. Позволим Alembic работать с sqlalchemy.url из alembic.ini
    # Исключение будет только если и там нет URL.
    print(
        "⚠️ DATABASE_URL is not set in environment. Alembic might use sqlalchemy.url from alembic.ini."
    )
    # raise ValueError("DATABASE_URL environment variable is not set.")

# Остальная часть файла остается без изменений...
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Создаем engine только если DATABASE_URL доступен
if DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
else:
    engine = None  # Или можно создать "заглушку" для Alembic, если нужно

AsyncSessionFactory = (
    sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    if engine
    else None
)

Base = declarative_base()

# ... (остальной код: get_db_session и т.д.)


# Исправим get_db_session, чтобы она не падала, если engine не создан
async def get_db_session():
    """
    Dependency для получения асинхронной сессии БД в FastAPI endpoints.
    Используется с `Depends(get_db_session)`.
    """
    if not AsyncSessionFactory:
        raise RuntimeError("Database engine is not configured. Check DATABASE_URL.")

    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
