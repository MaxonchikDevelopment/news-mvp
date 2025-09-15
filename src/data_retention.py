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
    Deletes old news items that are not referenced in feedback or user caches.
    This prevents deleting news that users might still interact with or have cached.

    Args:
        session: An active SQLAlchemy async session.
        days_old: The age threshold in days for deletion.

    Returns:
        The number of deleted news items.
    """
    if days_old <= 0:
        logger.info("News retention days set to 0 or less, skipping cleanup.")
        return 0

    logger.info(f"Starting cleanup of news items older than {days_old} days...")
    try:
        # Use a subquery or CTE to identify unreferenced news items
        # This query selects news items older than the threshold that
        # are NOT present in the feedback or user_news_cache tables.
        sql_delete = text(
            """
            WITH old_news AS (
                SELECT id FROM news_items
                WHERE fetched_at < NOW() - INTERVAL ':days_old DAYS'
            ),
            referenced_news AS (
                SELECT DISTINCT news_item_id AS id FROM feedback
                UNION
                SELECT DISTINCT news_item_id AS id FROM user_news_cache
            )
            DELETE FROM news_items
            WHERE id IN (SELECT id FROM old_news)
            AND id NOT IN (SELECT COALESCE(id, -1) FROM referenced_news); -- COALESCE handles potential NULLs
        """
        )

        # Note: Direct binding of interval might not work as expected in all drivers.
        # A safer approach is to calculate the date in Python and bind it.
        # Let's revise the query.

        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        sql_delete_safe = text(
            """
            WITH old_news AS (
                SELECT id FROM news_items
                WHERE fetched_at < :cutoff_date
            ),
            referenced_news AS (
                SELECT DISTINCT news_item_id AS id FROM feedback
                UNION
                SELECT DISTINCT news_item_id AS id FROM user_news_cache
            )
            DELETE FROM news_items
            WHERE id IN (SELECT id FROM old_news)
            AND id NOT IN (SELECT COALESCE(id, -1) FROM referenced_news);
        """
        )

        result = await session.execute(sql_delete_safe, {"cutoff_date": cutoff_date})
        deleted_count = result.rowcount
        await session.commit()  # Important: Commit the transaction
        logger.info(f"Deleted {deleted_count} old news items.")
        return deleted_count

    except Exception as e:
        logger.error(f"Failed to cleanup old news items: {e}")
        await session.rollback()  # Rollback on error
        # Depending on your error handling strategy, you might want to re-raise
        # raise # Re-raise if you want the pipeline to stop on cleanup failure
        return 0  # Or return 0 to continue pipeline despite cleanup error


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
            WHERE generated_at < :cutoff_date;
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


# Placeholder for future cleanup functions
# async def cleanup_old_feedback(...):
#     ...
# async def archive_aggregated_feedback(...):
#     ...


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
