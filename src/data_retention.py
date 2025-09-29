# src/data_retention.py
"""Automatic data retention and cleanup policies for the news database."""

import asyncio
import logging
import os  # Не забудь импортировать os для getenv
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, AsyncGenerator, Dict, Optional  # <-- Добавлен Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# --- Configuration ---
# Define data retention policies in days/months
NEWS_RETENTION_DAYS = int(os.getenv("NEWS_RETENTION_DAYS", 30))
USER_CACHE_RETENTION_DAYS = int(os.getenv("USER_CACHE_RETENTION_DAYS", 7))
FEEDBACK_RETENTION_MONTHS = int(os.getenv("FEEDBACK_RETENTION_MONTHS", 6))
# USER_NEWS_HISTORY_RETENTION_DAYS = 90 # Example for keeping user's viewed history

logger = logging.getLogger(__name__)

# --- Cleanup Functions ---


async def cleanup_old_news_items(
    session: AsyncSession, days_old: int = NEWS_RETENTION_DAYS
) -> int:
    """
    Deletes ALL old news items, regardless of references.
    This aligns with the concept that news is only relevant for one day.

    Args:
        session: An active SQLAlchemy async session.
        days_old: The age threshold in days for deletion.

    Returns:
        The number of deleted news items.
    """
    if days_old <= 0:
        logger.info("News retention days set to 0 or less, skipping cleanup.")
        return 0

    logger.info(f"Starting cleanup of ALL news items older than {days_old} days...")
    try:
        # --- ИСПРАВЛЕНИЕ: Удаление ВСЕХ старых новостей ---
        # Рассчитываем дату отсечки
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        # Простой и эффективный SQL-запрос для удаления
        sql_delete = text(
            """
            DELETE FROM news_items
            WHERE fetched_at < :cutoff_date;
            """
        )

        result = await session.execute(sql_delete, {"cutoff_date": cutoff_date})
        deleted_count = result.rowcount
        await session.commit()  # Important: Commit the transaction
        logger.info(
            f"Deleted {deleted_count} old news items (regardless of references)."
        )
        return deleted_count
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    except Exception as e:
        logger.error(f"Failed to cleanup old news items: {e}")
        await session.rollback()  # Rollback on error
        return 0


async def cleanup_expired_user_cache(
    session: AsyncSession, days_old: int = USER_CACHE_RETENTION_DAYS
) -> int:
    """
    Deletes expired entries from the user news cache.

    Args:
        session: An active SQLAlchemy async session.
        days_old: The age threshold in days for cache expiration.

    Returns:
        The number of deleted cache entries.
    """
    if days_old <= 0:
        logger.info("User cache retention days set to 0 or less, skipping cleanup.")
        return 0

    logger.info(f"Starting cleanup of user news cache older than {days_old} days...")
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        sql_delete = text(
            """
            DELETE FROM user_news_cache
            WHERE news_date < :cutoff_date;
            """
        )
        result = await session.execute(sql_delete, {"cutoff_date": cutoff_date})
        deleted_count = result.rowcount
        await session.commit()
        logger.info(f"Deleted {deleted_count} expired user cache entries.")
        return deleted_count

    except Exception as e:
        logger.error(f"Failed to cleanup expired user cache: {e}")
        await session.rollback()
        return 0


# --- Main Cleanup Orchestrator ---


async def perform_data_retention_cleanup(session: AsyncSession) -> Dict[str, int]:
    """
    Performs all configured data retention cleanup tasks.

    Args:
        session: An active SQLAlchemy async session.

    Returns:
        A dictionary with counts of deleted items for each task.
    """
    logger.info("--- Starting Data Retention Cleanup Tasks ---")

    # Словарь для подсчета удаленных элементов
    deleted_counts: Dict[str, int] = {}

    try:
        # Выполняем задачи очистки
        count_news = await cleanup_old_news_items(session, NEWS_RETENTION_DAYS)
        deleted_counts["cleanup_old_news_items"] = count_news

        count_cache = await cleanup_expired_user_cache(
            session, USER_CACHE_RETENTION_DAYS
        )
        deleted_counts["cleanup_expired_user_cache"] = count_cache

        logger.info("--- Data Retention Cleanup Tasks Completed ---")
        return deleted_counts

    except Exception as e:
        logger.critical(f"Critical failure during data retention cleanup: {e}")
        return deleted_counts  # Возвращаем то, что успели собрать
