# alembic/env.py
import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context

# --- ВАЖНО: Прямой импорт моделей ---
# Это гарантирует, что все модели будут зарегистрированы в Base.metadata
# до того, как Alembic попытается их проанализировать.
from src import models  # <-- ЭТО САМОЕ ГЛАВНОЕ ИЗМЕНЕНИЕ

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- НОВАЯ ЛОГИКА ---
# target_metadata определяется как None по умолчанию.
# Он будет загружен позже, если потребуется (например, для autogenerate).
target_metadata = None


def get_target_metadata():
    """Ленивая загрузка target_metadata из моделей."""
    global target_metadata
    if target_metadata is None:
        # Импортируем Base только когда это действительно нужно
        # Это предотвращает ошибки, если .env еще не загружен или DATABASE_URL не установлен
        # во время инициализации Alembic (например, при запуске `alembic --help`)
        from src.database import Base

        target_metadata = Base.metadata
    return target_metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # URL берется из alembic.ini
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_target_metadata(),  # <-- Используем ленивую загрузку
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Helper function to run migrations with a given connection."""
    context.configure(
        connection=connection,
        target_metadata=get_target_metadata(),  # <-- Используем ленивую загрузку
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Run migrations asynchronously."""
    # Импортируем engine внутри функции, чтобы избежать проблем на раннем этапе
    from src.database import engine

    # Проверяем, является ли engine асинхронным
    if not isinstance(engine, AsyncEngine):
        raise RuntimeError("Expected an async engine for migrations.")

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    # --- Вариант для синхронного движка (если бы использовали psycopg2) ---
    # connectable = engine_from_config(
    #     config.get_section(config.config_ini_section, {}),
    #     prefix="sqlalchemy.",
    #     poolclass=pool.NullPool,
    # )
    # with connectable.connect() as connection:
    #     do_run_migrations(connection)
    # --- Конец синхронного варианта ---

    # --- Вариант для асинхронного движка (наш случай) ---
    # Так как наши модели и engine асинхронные, нам нужно запустить миграции асинхронно.
    # Alembic CLI по умолчанию синхронный, поэтому мы оборачиваем асинхронный запуск.
    asyncio.run(run_async_migrations())
    # --- Конец асинхронного варианта ---


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
