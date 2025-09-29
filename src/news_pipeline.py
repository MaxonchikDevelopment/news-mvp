# src/news_pipeline.py
"""
Complete news processing pipeline with real user integration, feedback, caching, and data retention.

Optimized architecture:
1) Background task fetches/classifies news ONCE for the whole system, generates YNK summaries,
   and saves unique news to DB (table: news_items).
2) Background task generates personalized TOP-7 bundles for ALL users from pre-processed news
   and caches them (table: user_news_cache).
3) Background task generates personalized podcast scripts for PREMIUM users and caches them
   in the same cache bundle (user_news_cache).
4) API-like methods only read prebuilt bundles from cache to respond instantly.

This module is intended to be both:
- A library class (`NewsProcessingPipeline`) to be imported and called from your app,
- A CLI entry point to run the daily background pipeline or test a single user.
"""

import asyncio
import inspect
import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union

# ---------------------------
# Path setup for internal imports
# ---------------------------


def setup_paths() -> None:
    """Ensure project paths are in sys.path for local imports to work."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    for path in (project_root, current_dir):
        if path not in sys.path:
            sys.path.insert(0, path)


setup_paths()

# ---------------------------
# Imports of project modules (with safe fallbacks/logging)
# ---------------------------

try:
    from news_fetcher import SmartNewsFetcher

    print("✅ Imported SmartNewsFetcher successfully")
except ImportError as e:
    print(f"❌ Failed to import SmartNewsFetcher: {e}")
    sys.exit(1)

try:
    from user_profile import USER_PROFILES, get_user_profile

    print("✅ Imported user_profile successfully")
except ImportError as e:
    print(f"❌ Failed to import user_profile: {e}")
    sys.exit(1)

try:
    from cache_manager import get_cache_manager

    print("✅ Imported cache_manager successfully")
except ImportError as e:
    print(f"❌ Failed to import cache_manager: {e}")
    sys.exit(1)

try:
    from summarizer import summarize_news

    print("✅ Imported summarizer successfully")
except ImportError as e:
    print(f"❌ Failed to import summarizer: {e}")
    summarize_news = None  # module is optional

try:
    from feedback_system import feedback_system

    print("✅ Imported feedback_system successfully")
except ImportError as e:
    print(f"❌ Failed to import feedback_system: {e}")
    feedback_system = None  # optional

# Data retention (optional)
try:
    from data_retention import perform_data_retention_cleanup

    DATA_RETENTION_ENABLED = True
    print("✅ Imported data_retention successfully")
except ImportError as e:
    print(f"⚠️ Data retention module not available: {e}. Cleanup will be skipped.")
    perform_data_retention_cleanup = None
    DATA_RETENTION_ENABLED = False

# Database and models
try:
    from sqlalchemy import (  # noqa: F401 (delete may be used in retention)
        delete,
        select,
    )

    from database import AsyncSessionFactory  # Async session factory
    from src.models import NewsItem
    from src.models import User as DBUser
    from src.models import UserNewsCache
    from src.models import UserProfile as DBUserProfile

    DATABASE_AVAILABLE = True
    print("✅ Imported database and models successfully")
except ImportError as e:
    print(f"⚠️ Database or models not fully available: {e}")
    AsyncSessionFactory = None
    NewsItem = None
    DBUser = None
    DBUserProfile = None
    UserNewsCache = None
    select = None
    delete = None
    DATABASE_AVAILABLE = False

# Podcast generator (optional)
try:
    from src.podcast_generator import get_podcast_generator

    PODCAST_GENERATOR_AVAILABLE = True
    print("✅ Imported podcast_generator successfully")
except ImportError as e:
    print(f"⚠️ Podcast generator module not available: {e}. Podcasts will be skipped.")
    get_podcast_generator = None
    PODCAST_GENERATOR_AVAILABLE = False


class NewsProcessingPipeline:
    """
    Orchestrates the complete news processing workflow for personalized delivery.

    Responsibilities:
    - Fetch & classify global news once;
    - Persist unique news into DB (with AI analysis inc. YNK);
    - Build & cache per-user TOP-7 bundles;
    - Generate & cache per-user podcast scripts (for premium users);
    - Provide API-like methods to read cached data quickly.
    """

    def __init__(self, max_workers: int = 5) -> None:
        """
        Initialize the pipeline.

        Args:
            max_workers: Reserved for potential concurrency usage (not used directly here).
        """
        self.max_workers = max_workers
        self.fetcher = SmartNewsFetcher()
        self.cache = get_cache_manager()
        self.feedback_system = feedback_system
        self.summarize_news_func = summarize_news
        self.podcast_generator = (
            get_podcast_generator() if PODCAST_GENERATOR_AVAILABLE else None
        )
        self.processed_news_count = 0
        self.total_processing_time = 0.0
        print(
            "🚀 NewsProcessingPipeline initialized with enhanced SmartNewsFetcher and PodcastGenerator"
        )

    # ---------- utility ----------

    async def _maybe_await(self, value):
        """
        Await the value if it's awaitable; otherwise return it as-is.

        This makes the pipeline compatible with both sync and async podcast generators.
        """
        if inspect.isawaitable(value):
            return await value
        return value

    # -------------------------------------------------------
    # Users
    # -------------------------------------------------------

    def get_all_users(self) -> List[Any]:
        """
        Return all in-memory/system users (fallback when DB is unavailable).
        """
        users: List[Any] = []
        for user_id in USER_PROFILES.keys():
            user = get_user_profile(user_id)
            if user:
                users.append(user)
        print(f"👥 Loaded {len(users)} users from system")
        return users

    async def get_all_users_from_db(self) -> List[Dict[str, Any]]:
        """
        Fetch all registered users from the database.

        Returns:
            A list of dicts {id, email, profile}, where profile is a normalized dict.
            If DB is unavailable, returns converted system users as a fallback.
        """
        if not (
            DATABASE_AVAILABLE and AsyncSessionFactory and DBUser and DBUserProfile
        ):
            print(
                "⚠️ Database not configured for fetching users. Returning system users."
            )
            system_users = self.get_all_users()
            db_user_list: List[Dict[str, Any]] = []
            for user in system_users:
                user_dict = self._convert_user_profile_to_dict(user)
                db_user_list.append(
                    {
                        "id": user_dict.get("user_id"),
                        "email": f"{user_dict.get('user_id')}@example.com",
                        "profile": user_dict,
                    }
                )
            return db_user_list

        async with AsyncSessionFactory() as db_session:
            try:
                # Join User and UserProfile (outer join to allow users without profiles)
                stmt = select(DBUser, DBUserProfile).join(DBUserProfile, isouter=True)
                result = await db_session.execute(stmt)
                db_users_with_profiles = result.all()

                users_list: List[Dict[str, Any]] = []
                for db_user, db_profile in db_users_with_profiles:
                    users_list.append(
                        {
                            "id": db_user.id,
                            "email": db_user.email,
                            "profile": {
                                "user_id": db_user.id,
                                "locale": db_profile.locale if db_profile else "US",
                                "language": "en",
                                "city": None,
                                "interests": db_profile.interests if db_profile else [],
                            }
                            if db_profile
                            else None,
                        }
                    )

                print(f"👥 Loaded {len(users_list)} users from database")
                return users_list
            except Exception as e:
                print(f"⚠️ Error fetching users from DB: {e}")
                return []

    @staticmethod
    def _safe_attr(obj: Any, name: str, default: Any) -> Any:
        """Helper: getattr with default for non-standard objects."""
        try:
            return getattr(obj, name, default)
        except Exception:
            return default

    def _convert_user_profile_to_dict(self, user_profile: Any) -> Dict[str, Any]:
        """
        Convert a user profile (object or dict) to a normalized dictionary.
        """
        if isinstance(user_profile, dict):
            return user_profile
        elif hasattr(user_profile, "__dict__"):
            return user_profile.__dict__
        else:
            # Fallback for unexpected types (e.g., SimpleNamespace or namedtuples)
            print(
                f"⚠️ Unexpected user profile type: {type(user_profile)}. Attempting attribute access."
            )
            return {
                "user_id": self._safe_attr(user_profile, "user_id", "unknown"),
                "locale": self._safe_attr(user_profile, "locale", "US"),
                "language": self._safe_attr(user_profile, "language", "en"),
                "city": self._safe_attr(user_profile, "city", ""),
                "interests": self._safe_attr(user_profile, "interests", []),
            }

    # -------------------------------------------------------
    # Persistence of news to DB
    # -------------------------------------------------------

    async def _save_news_items_to_db(
        self, news_bundle: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """
        Persist unique news (by URL) to DB and ensure ai_analysis includes YNK summary.

        Args:
            news_bundle: Dict[category -> List[article dict]]
        """
        if not (DATABASE_AVAILABLE and AsyncSessionFactory and NewsItem):
            print("⚠️ Database not configured for saving news items. Skipping.")
            return

        # Flatten all articles from the bundle
        all_articles: List[Dict[str, Any]] = []
        for category_articles in news_bundle.values():
            if isinstance(category_articles, list):
                all_articles.extend(category_articles)

        # Deduplicate by URL
        unique_urls: Set[str] = set()
        articles_to_process: List[Dict[str, Any]] = []
        for article in all_articles:
            url = article.get("url")
            if url and url not in unique_urls:
                unique_urls.add(url)
                articles_to_process.append(article)

        async with AsyncSessionFactory() as db_session:
            try:
                for article in articles_to_process:
                    # Try finding existing item by URL
                    stmt = select(NewsItem).where(NewsItem.url == article["url"])
                    result = await db_session.execute(stmt)
                    existing_item = result.scalar_one_or_none()

                    if existing_item:
                        # Use existing ID and update ai_analysis if incomplete
                        article["id"] = existing_item.id
                        needs_ai_update = (
                            not existing_item.ai_analysis
                            or not isinstance(existing_item.ai_analysis, dict)
                            or not existing_item.ai_analysis.get("ynk_summary")
                            or "relevance_score" not in existing_item.ai_analysis
                            or "confidence" not in existing_item.ai_analysis
                        )

                        if needs_ai_update:
                            print(
                                f"  🔄 Updating incomplete ai_analysis for existing item ID {existing_item.id}..."
                            )

                            ynk_summary = article.get("ynk_summary")
                            if not ynk_summary:
                                ynk_summary = self._generate_ynk_summary(article)
                                article["ynk_summary"] = ynk_summary

                            relevance_score = article.get("relevance_score", 0)
                            confidence = article.get("confidence", 0)

                            existing_item.ai_analysis = {
                                "relevance_score": relevance_score,
                                "confidence": confidence,
                                "ynk_summary": ynk_summary,
                            }
                            db_session.add(existing_item)
                            await db_session.commit()
                            await db_session.refresh(existing_item)
                            print(
                                f"  ✅ Updated ai_analysis for item ID {existing_item.id}."
                            )
                    else:
                        # Create new NewsItem
                        external_id = article.get("external_id") or article["url"]

                        # Ensure YNK exists before save
                        ynk_summary = article.get("ynk_summary")
                        if not ynk_summary:
                            ynk_summary = self._generate_ynk_summary(article)
                            article["ynk_summary"] = ynk_summary

                        new_item = NewsItem(
                            external_id=external_id,
                            source_name=article.get(
                                "source_name", article.get("source", "Unknown")
                            ),
                            title=article["title"],
                            url=article["url"],
                            category=article.get("category", "unknown"),
                            subcategory=article.get("subcategory"),
                            importance_score=article.get("importance_score", 0),
                            ai_analysis={
                                "relevance_score": article.get("relevance_score", 0),
                                "confidence": article.get("confidence", 0),
                                "ynk_summary": ynk_summary,
                            },
                            fetched_at=datetime.utcnow(),
                        )

                        db_session.add(new_item)
                        await db_session.commit()
                        await db_session.refresh(new_item)
                        article["id"] = new_item.id

                print(
                    f"✅ Saved/Checked {len(articles_to_process)} unique news items to DB."
                )
            except Exception as e:
                print(f"⚠️ Error saving news items to DB: {e}")
                await db_session.rollback()

    def _generate_ynk_summary(self, article: Dict[str, Any]) -> str:
        """
        Generate YNK (Why eN/Not to care) summary using the optional summarizer module.

        Fallbacks:
        - If summarizer is missing, return a placeholder text.
        - If no content available, return a short reason.
        """
        if not self.summarize_news_func:
            return "Summary generation module (summarizer.py) not available."

        try:
            news_text = (
                article.get("content", "")
                or article.get("description", "")
                or article.get("title", "")
            )
            if not news_text.strip():
                return "No content, description, or title available for summary."

            category = article.get("category", "general")
            summary = self.summarize_news_func(news_text, category)
            return summary
        except Exception as e:
            return f"Could not generate summary. Error: {e}"

    # -------------------------------------------------------
    # Selection / Personalization
    # -------------------------------------------------------

    def _select_top_articles_for_user(
        self,
        classified_news_list: Union[
            List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]
        ],
        user_profile: Union[Dict[str, Any], Any],
    ) -> List[Dict[str, Any]]:
        """
        Select the TOP-7 articles for a specific user from ALREADY CLASSIFIED news.

        Accepts either:
        - flat list[List[article]], or
        - dict[category -> list[article]] (will be flattened).

        Guarantee logic:
        - If user has specific subcategory interests, try to include 1 article per subcategory
          if it meets MIN_RELEVANCE_THRESHOLD.
        - Then try to include 1 per main category of interest, also thresholded.
        - Fill the remainder with best overall articles by relevance.

        Returns:
            A list of up to 7 articles sorted by relevance (highest first).
        """

        # Normalize input to a flat list
        if isinstance(classified_news_list, dict):
            flat_articles: List[Dict[str, Any]] = []
            for v in classified_news_list.values():
                if isinstance(v, list):
                    flat_articles.extend(v)
        elif isinstance(classified_news_list, list):
            flat_articles = classified_news_list
        else:
            flat_articles = []

        user_profile_dict = self._convert_user_profile_to_dict(user_profile)
        selected_articles: List[Dict[str, Any]] = []
        seen_titles: Set[str] = set()

        user_interests = user_profile_dict.get("interests", [])
        main_categories = [i for i in user_interests if isinstance(i, str)]
        specific_subcategories: Set[str] = set()

        # Collect nested subcategories found in dict interests, e.g. {"sports": ["nba", "epl"]}
        for interest in user_interests:
            if isinstance(interest, dict):
                for _, subcats in interest.items():
                    if isinstance(subcats, list):
                        specific_subcategories.update(subcats)

        MIN_RELEVANCE_THRESHOLD = 0.40

        # Helper to compute article relevance, reading from top-level or nested ai_analysis
        def rel(a: Dict[str, Any]) -> float:
            if "relevance_score" in a:
                return float(a.get("relevance_score") or 0)
            return float(a.get("ai_analysis", {}).get("relevance_score") or 0)

        # 1) Guarantee specific subcategories (ordered by learned preference if available)
        sorted_specific_subcats = list(specific_subcategories)
        if self.feedback_system:
            uid = user_profile_dict.get("user_id", "unknown_user")
            sorted_specific_subcats.sort(
                key=lambda s: self.feedback_system.get_user_preference(uid, s),
                reverse=True,
            )

        for subcategory in sorted_specific_subcats:
            matching = []
            for art in flat_articles:
                art_subcats = [
                    art.get("sports_subcategory"),
                    art.get("economy_subcategory"),
                    art.get("tech_subcategory"),
                ]
                if subcategory in art_subcats:
                    matching.append(art)
            matching.sort(key=rel, reverse=True)

            for art in matching:
                tk = (art.get("title") or "").lower()
                if (
                    tk not in seen_titles
                    and len(selected_articles) < 7
                    and rel(art) >= MIN_RELEVANCE_THRESHOLD
                ):
                    selected_articles.append(art)
                    seen_titles.add(tk)
                    break  # take only one for this subcategory

        # 2) Guarantee main categories (ordered by learned preference if available)
        sorted_main = list(main_categories)
        if self.feedback_system:
            uid = user_profile_dict.get("user_id", "unknown_user")
            sorted_main.sort(
                key=lambda c: self.feedback_system.get_user_preference(uid, c),
                reverse=True,
            )

        for cat in sorted_main:
            if len(selected_articles) >= 7:
                break
            cat_arts = [a for a in flat_articles if a.get("category") == cat]
            cat_arts.sort(key=rel, reverse=True)
            for art in cat_arts:
                tk = (art.get("title") or "").lower()
                if (
                    tk not in seen_titles
                    and len(selected_articles) < 7
                    and rel(art) >= MIN_RELEVANCE_THRESHOLD
                ):
                    selected_articles.append(art)
                    seen_titles.add(tk)
                    break  # take only one for this main category

        # 3) Fill the remainder with best-overall by relevance
        if len(selected_articles) < 7:
            all_sorted = sorted(flat_articles, key=rel, reverse=True)
            for art in all_sorted:
                if len(selected_articles) >= 7:
                    break
                tk = (art.get("title") or "").lower()
                if tk not in seen_titles:
                    selected_articles.append(art)
                    seen_titles.add(tk)

        # Final sort by relevance desc
        final_selection = selected_articles[:7]
        final_selection.sort(key=rel, reverse=True)
        print(
            f"🎯 Final news bundle ready: {len(final_selection)} articles selected for TOP-7"
        )
        return final_selection

    # -------------------------------------------------------
    # Data retention
    # -------------------------------------------------------

    async def _run_data_retention_cleanup(self) -> None:
        """
        Run data retention cleanup tasks (if module and DB are available).
        """
        if not (
            DATA_RETENTION_ENABLED
            and DATABASE_AVAILABLE
            and AsyncSessionFactory
            and perform_data_retention_cleanup
        ):
            print(
                "⚠️ Data retention is disabled or database is not configured. Skipping cleanup."
            )
            return

        print("--- Initiating Automatic Data Retention Cleanup ---")
        try:
            async with AsyncSessionFactory() as session:
                deleted_counts = await perform_data_retention_cleanup(session)
                print("--- Data Retention Cleanup Summary ---")
                for task, count in deleted_counts.items():
                    print(f"  ✅ {task}: {count} items")
                print("--------------------------------------")
        except Exception as e:
            print(f"⚠️ Data retention cleanup failed: {e}")

    # -------------------------------------------------------
    # Background tasks (NEW architecture)
    # -------------------------------------------------------

    async def fetch_and_classify_all_news(self) -> List[Dict[str, Any]]:
        """
        Background Task 1:
        - Fetches a broad set of news for many categories,
        - Saves unique news to DB (ensuring ai_analysis with YNK),
        - Returns a list of saved items (converted from DB models).

        Returns:
            List of dicts representing persisted news items.
        """
        print("\n--- [BACKGROUND TASK 1] Fetching and Classifying ALL News ---")

        # Wide-coverage "dummy" profile to gather everything we care about
        dummy_profile = {
            "user_id": "background_processor",
            "locale": "US",
            "language": "en",
            "interests": [
                "economy_finance",
                "technology_ai_science",
                "politics_geopolitics",
                "healthcare_pharma",
                "culture_media_entertainment",
                "sports",
                "transport_auto_aviation",
                "lifestyle_travel_tourism",
            ],
        }

        start_time = time.time()
        print("📡 Fetching global news bundle for all categories...")
        news_bundle = self.fetcher.fetch_daily_news_bundle(dummy_profile)
        fetch_time = time.time() - start_time
        try:
            raw_total = sum(len(arts) for arts in news_bundle.values())
        except Exception:
            # If fetcher ever returns a flat list accidentally
            raw_total = len(news_bundle) if isinstance(news_bundle, list) else 0
        print(f"📦 Raw articles collected: {raw_total} (in {fetch_time:.2f}s)")

        # Save to DB (also ensures AI analysis/YNK presence)
        await self._save_news_items_to_db(news_bundle)
        save_time = time.time() - start_time - fetch_time
        print(f"💾 News saved/classified/YNK'd to DB (in {save_time:.2f}s)")

        # Load back from DB (IDs + ai_analysis preserved)
        if not (DATABASE_AVAILABLE and AsyncSessionFactory and NewsItem and select):
            print("⚠️ Cannot fetch saved news from DB. Returning empty list.")
            return []

        async with AsyncSessionFactory() as db_session:
            try:
                since = datetime.utcnow() - timedelta(days=1)
                stmt = select(NewsItem).where(NewsItem.fetched_at >= since)
                result = await db_session.execute(stmt)
                saved_news_items = result.scalars().all()

                saved_news_list: List[Dict[str, Any]] = []
                for item in saved_news_items:
                    saved_news_list.append(
                        {
                            "id": item.id,
                            "external_id": item.external_id,
                            "source_name": item.source_name,
                            "title": item.title,
                            "url": item.url,
                            "category": item.category,
                            "subcategory": item.subcategory,
                            "importance_score": item.importance_score,
                            "ai_analysis": item.ai_analysis,  # includes relevance_score, confidence, ynk_summary
                            "fetched_at": item.fetched_at.isoformat()
                            if item.fetched_at
                            else None,
                        }
                    )

                print(
                    f"📤 Fetched {len(saved_news_list)} classified news items with IDs from DB."
                )
                return saved_news_list
            except Exception as e:
                print(f"⚠️ Error fetching saved news from DB: {e}")
                return []

    async def generate_and_cache_bundles_for_all_users(
        self, classified_news_list: List[Dict[str, Any]]
    ) -> None:
        """
        Background Task 2:
        - For each user, builds a personalized TOP-7 from already classified news,
        - Stores the bundle in user_news_cache for today's date.

        Args:
            classified_news_list: A flat list of news dicts (with ids and ai_analysis).
        """
        print(
            "\n--- [BACKGROUND TASK 2] Generating Personalized Bundles for ALL Users ---"
        )

        if not classified_news_list:
            print("⚠️ No classified news provided. Skipping bundle generation.")
            return

        all_users = await self.get_all_users_from_db()
        if not all_users:
            print("⚠️ No users found in database. Skipping bundle generation.")
            return

        if not (
            DATABASE_AVAILABLE and AsyncSessionFactory and UserNewsCache and select
        ):
            print("⚠️ Database not configured for caching user bundles. Skipping.")
            return

        print(f"👥 Generating bundles for {len(all_users)} users...")
        async with AsyncSessionFactory() as db_session:
            try:
                today = date.today()

                for user_data in all_users:
                    user_id = user_data["id"]
                    user_email = user_data["email"]
                    user_profile = user_data.get("profile")

                    if not user_profile:
                        print(
                            f"⚠️ No profile found for user {user_email} (ID: {user_id}). Skipping."
                        )
                        continue

                    print(
                        f"  🧠 Generating bundle for user {user_email} (ID: {user_id})..."
                    )

                    top_7_articles = self._select_top_articles_for_user(
                        classified_news_list, user_profile
                    )

                    # Promote ai_analysis fields to top-level for quick API usage
                    prepared_top_7: List[Dict[str, Any]] = []
                    for article in top_7_articles:
                        prepared = dict(article)
                        ai = article.get("ai_analysis", {})
                        prepared["relevance_score"] = prepared.get(
                            "relevance_score", ai.get("relevance_score", 0)
                        )
                        prepared["confidence"] = prepared.get(
                            "confidence", ai.get("confidence", 0)
                        )
                        prepared["ynk_summary"] = prepared.get(
                            "ynk_summary", ai.get("ynk_summary", "N/A")
                        )
                        prepared_top_7.append(prepared)

                    cache_data = {
                        "generated_at": datetime.utcnow().isoformat(),
                        "top_7": prepared_top_7,
                    }

                    # Upsert today's cache entry
                    stmt_check = select(UserNewsCache).where(
                        UserNewsCache.user_id == user_id,
                        UserNewsCache.news_date == today,
                    )
                    result = await db_session.execute(stmt_check)
                    existing_cache = result.scalar_one_or_none()

                    if existing_cache:
                        existing_cache.news_bundle = cache_data
                        existing_cache.generated_at = datetime.utcnow()
                        print(f"    🔄 Updated cache for user {user_email}.")
                    else:
                        new_cache_entry = UserNewsCache(
                            user_id=user_id,
                            news_date=today,
                            news_bundle=cache_data,
                        )
                        db_session.add(new_cache_entry)
                        print(f"    ✅ Cached bundle for user {user_email}.")

                await db_session.commit()
                print(
                    f"🎉 All {len(all_users)} user bundles cached successfully for {today}."
                )
            except Exception as e:
                print(f"⚠️ Error generating/caching bundles for users: {e}")
                await db_session.rollback()

    async def generate_and_cache_podcasts_for_premium_users(
        self, classified_news_list: List[Dict[str, Any]]
    ) -> None:
        """
        Background Task 3:
        - For each premium user, generate a podcast script from their personalized TOP-7,
        - Store the script alongside the TOP-7 in the user cache bundle.

        Args:
            classified_news_list: A flat list of news dicts (with ids and ai_analysis).
        """
        print(
            "\n--- [BACKGROUND TASK 3] Generating Personalized Podcasts for ALL Premium Users ---"
        )

        if not classified_news_list:
            print("⚠️ No classified news provided. Skipping podcast generation.")
            return

        if not (PODCAST_GENERATOR_AVAILABLE and self.podcast_generator):
            print("⚠️ Podcast generator is not available. Skipping podcast generation.")
            return

        all_users = await self.get_all_users_from_db()
        if not all_users:
            print("⚠️ No users found in database. Skipping podcast generation.")
            return

        # TEMPORARY premium check: even user IDs are premium (replace with real logic)
        premium_users = [
            user
            for user in all_users
            if isinstance(user.get("id"), int) and user["id"] % 2 == 0
        ]
        if not premium_users:
            print("⚠️ No premium users found in database. Skipping podcast generation.")
            return

        if not (
            DATABASE_AVAILABLE and AsyncSessionFactory and UserNewsCache and select
        ):
            print("⚠️ Database not configured for caching podcasts. Skipping.")
            return

        print(f"👥 Generating podcasts for {len(premium_users)} premium users...")
        async with AsyncSessionFactory() as db_session:
            try:
                today = date.today()

                for user_data in premium_users:
                    user_id = user_data["id"]
                    user_email = user_data["email"]
                    user_profile = user_data.get("profile")

                    if not user_profile:
                        print(
                            f"⚠️ No profile found for premium user {user_email} (ID: {user_id}). Skipping."
                        )
                        continue

                    print(
                        f"  🎙️  Generating podcast for premium user {user_email} (ID: {user_id})..."
                    )

                    top_7_articles = self._select_top_articles_for_user(
                        classified_news_list, user_profile
                    )

                    prepared_top_7: List[Dict[str, Any]] = []
                    for article in top_7_articles:
                        prepared = dict(article)
                        ai = article.get("ai_analysis", {})
                        prepared["relevance_score"] = prepared.get(
                            "relevance_score", ai.get("relevance_score", 0)
                        )
                        prepared["confidence"] = prepared.get(
                            "confidence", ai.get("confidence", 0)
                        )
                        prepared["ynk_summary"] = prepared.get(
                            "ynk_summary", ai.get("ynk_summary", "N/A")
                        )
                        prepared_top_7.append(prepared)

                    # --- Generate podcast script (sync or async safe) ---
                    try:
                        print(
                            f"    🧠 Calling podcast generator for user {user_email}..."
                        )
                        maybe_result = self.podcast_generator.generate_podcast_script(
                            user_profile, prepared_top_7
                        )
                        podcast_script = await self._maybe_await(maybe_result)
                        print(f"    ✅ Podcast script generated for user {user_email}.")
                    except Exception as e:
                        print(
                            f"    ⚠️ Error generating podcast script for user {user_email}: {e}"
                        )
                        podcast_script = "Sorry, the podcast script could not be generated at this time."

                    # Upsert today's cache entry (attach podcast_script)
                    stmt_check = select(UserNewsCache).where(
                        UserNewsCache.user_id == user_id,
                        UserNewsCache.news_date == today,
                    )
                    result = await db_session.execute(stmt_check)
                    existing_cache = result.scalar_one_or_none()

                    if existing_cache:
                        bundle = existing_cache.news_bundle or {}
                        bundle["top_7"] = prepared_top_7  # ensure top_7 present
                        bundle["podcast_script"] = podcast_script
                        existing_cache.news_bundle = bundle
                        existing_cache.generated_at = datetime.utcnow()
                        print(
                            f"    🔄 Updated cache with podcast for user {user_email}."
                        )
                    else:
                        cache_data = {
                            "generated_at": datetime.utcnow().isoformat(),
                            "top_7": prepared_top_7,
                            "podcast_script": podcast_script,
                        }
                        new_cache_entry = UserNewsCache(
                            user_id=user_id,
                            news_date=today,
                            news_bundle=cache_data,
                        )
                        db_session.add(new_cache_entry)
                        print(
                            f"    ✅ Cached bundle with podcast for user {user_email}."
                        )

                await db_session.commit()
                print(
                    f"🎉 All {len(premium_users)} premium user podcasts cached successfully for {today}."
                )
            except Exception as e:
                print(f"⚠️ Error generating/caching podcasts for premium users: {e}")
                await db_session.rollback()

    # -------------------------------------------------------
    # API-like read helpers
    # -------------------------------------------------------

    async def get_cached_news_bundle_for_user(
        self, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Return cached news bundle for the given user ID and today's date.

        Returns:
            The cached `news_bundle` dict that contains at least {"top_7": [...]},
            or None if not found / DB not configured.
        """
        if not (
            DATABASE_AVAILABLE and AsyncSessionFactory and UserNewsCache and select
        ):
            print("⚠️ Database not configured for fetching cached news.")
            return None

        async with AsyncSessionFactory() as db_session:
            try:
                today = date.today()
                stmt = select(UserNewsCache).where(
                    UserNewsCache.user_id == user_id,
                    UserNewsCache.news_date == today,
                )
                result = await db_session.execute(stmt)
                cache_entry = result.scalar_one_or_none()
                if cache_entry:
                    print(f"✅ Found cached news bundle for user ID {user_id}.")
                    return cache_entry.news_bundle
                else:
                    print(
                        f"⚠️ No cached news bundle found for user ID {user_id} for {today}."
                    )
                    return None
            except Exception as e:
                print(f"⚠️ Error fetching cached news for user {user_id}: {e}")
                return None

    async def get_cached_podcast_script_for_user(
        self, user_id: int
    ) -> Optional[Dict[str, str]]:
        """
        Return the cached podcast script for the given user ID and today's date.

        Returns:
            {"script": "..."} if present; otherwise None.
        """
        if not (
            DATABASE_AVAILABLE and AsyncSessionFactory and UserNewsCache and select
        ):
            print("⚠️ Database not configured for fetching cached podcast.")
            return None

        async with AsyncSessionFactory() as db_session:
            try:
                today = date.today()
                stmt = select(UserNewsCache).where(
                    UserNewsCache.user_id == user_id,
                    UserNewsCache.news_date == today,
                )
                result = await db_session.execute(stmt)
                cache_entry = result.scalar_one_or_none()

                if cache_entry and cache_entry.news_bundle:
                    podcast_script = cache_entry.news_bundle.get("podcast_script")
                    if podcast_script:
                        print(f"✅ Found cached podcast script for user ID {user_id}.")
                        return {"script": podcast_script}
                    else:
                        print(
                            f"⚠️ No podcast script found in cache for user ID {user_id} for {today}."
                        )
                        return None
                else:
                    print(
                        f"⚠️ No cached news bundle found for user ID {user_id} for {today}."
                    )
                    return None
            except Exception as e:
                print(f"⚠️ Error fetching cached podcast for user {user_id}: {e}")
                return None

    async def generate_podcast_script_for_user(
        self, user_id: int, top_7_articles: List[Dict[str, Any]]
    ) -> Optional[Dict[str, str]]:
        """
        Generate a personalized podcast script for a user based on their TOP-7.

        Args:
            user_id: DB user ID.
            top_7_articles: The user's TOP-7 articles.

        Returns:
            {"script": "..."} or None on error.
        """
        print(f"🎙️  Generating podcast script for user ID: {user_id}...")

        if not top_7_articles:
            print(
                f"⚠️  No TOP-7 articles provided for user {user_id}. Cannot generate podcast."
            )
            return None
        if not self.podcast_generator:
            print(f"⚠️  Podcast generator not available for user {user_id}.")
            return None
        if not (
            DATABASE_AVAILABLE
            and AsyncSessionFactory
            and DBUser
            and DBUserProfile
            and select
        ):
            print(
                f"⚠️  Database not configured (users/profiles). Cannot generate podcast for user {user_id}."
            )
            return None

        try:
            # Load user profile from DB first (for premium flag or additional context)
            async with AsyncSessionFactory() as db_session:
                stmt = (
                    select(DBUser, DBUserProfile)
                    .join(DBUserProfile, isouter=True)
                    .where(DBUser.id == user_id)
                )
                result = await db_session.execute(stmt)
                db_user_with_profile = result.first()

                if not db_user_with_profile:
                    print(
                        f"⚠️  User with ID {user_id} not found in DB for podcast generation."
                    )
                    return None

                db_user, db_profile = db_user_with_profile
                user_profile_data = {
                    "user_id": db_user.id,
                    "email": db_user.email,
                    "locale": db_profile.locale if db_profile else "US",
                    "language": "en",
                    "city": None,
                    "interests": db_profile.interests if db_profile else [],
                    "is_premium": getattr(db_profile, "is_premium", False)
                    if db_profile
                    else False,
                }

            # --- Generate script (sync or async safe) ---
            maybe_result = self.podcast_generator.generate_podcast_script(
                user_profile_data, top_7_articles
            )
            podcast_script = await self._maybe_await(maybe_result)

            print(f"✅  Podcast script generated successfully for user ID {user_id}.")
            return {"script": podcast_script}
        except Exception as e:
            print(f"❌  Error generating podcast script for user {user_id}: {e}")
            return None

    # -------------------------------------------------------
    # Legacy compatibility (API entry)
    # -------------------------------------------------------

    async def process_daily_news(
        self, user_preferences: Union[Dict[str, Any], Any]
    ) -> Dict[str, Any]:
        """
        API-style method: returns the cached 'top_7' for a user for today.

        - Determines user ID from the given preferences (tries 'user_id' or fallback by email).
        - Reads cache via DB and returns {"top_7": [...]} or an informative message.
        """
        user_prefs_dict = self._convert_user_profile_to_dict(user_preferences)
        user_id_raw = user_prefs_dict.get("user_id")

        # Try to get DB user id
        db_user_id: Optional[int] = None
        if isinstance(user_id_raw, int):
            db_user_id = user_id_raw
        elif isinstance(user_id_raw, str) and user_id_raw.isdigit():
            db_user_id = int(user_id_raw)
        else:
            # Fallback: try to find user by email
            email = user_prefs_dict.get("email") or f"{user_id_raw}@example.com"
            if DATABASE_AVAILABLE and AsyncSessionFactory and DBUser and select:
                async with AsyncSessionFactory() as db_session:
                    try:
                        stmt = select(DBUser).where(DBUser.email == email)
                        result = await db_session.execute(stmt)
                        db_user = result.scalar_one_or_none()
                        if db_user:
                            db_user_id = db_user.id
                    except Exception as e:
                        print(f"⚠️ Error finding user ID for {email}: {e}")

        if db_user_id is None:
            print(
                f"⚠️ Could not determine database user ID for preferences {user_id_raw}. Cannot fetch from cache."
            )
            return {
                "top_7": [],
                "error": "User not found or ID invalid for cache lookup.",
            }

        print(f"\n--- [API REQUEST] Fetching cached news for user ID: {db_user_id} ---")
        cached_bundle = await self.get_cached_news_bundle_for_user(db_user_id)

        if cached_bundle and "top_7" in cached_bundle:
            print(f"✅ Returned cached TOP-7 for user ID {db_user_id}.")
            return cached_bundle
        else:
            print(
                f"⚠️ No cached news available for user ID {db_user_id}. Please run the background daily pipeline first."
            )
            return {
                "top_7": [],
                "message": "Your personalized news feed is being prepared. Please try again in a few minutes.",
            }

    # -------------------------------------------------------
    # Main orchestrator (background daily run)
    # -------------------------------------------------------

    async def run_full_daily_pipeline(self) -> None:
        """
        Run the full daily pipeline:
        1) Fetch & classify & persist all news,
        2) Generate & cache per-user bundles,
        3) Generate & cache per-premium-user podcasts,
        4) Run data retention cleanup.
        """
        print("🚀 Starting NEW Full Daily News Pipeline Run (Background Task)...")
        pipeline_start_time = time.time()

        # 1) Fetch and classify all news
        classified_news = await self.fetch_and_classify_all_news()

        # 2) Generate and cache bundles for all users
        await self.generate_and_cache_bundles_for_all_users(classified_news)

        # 3) Generate and cache podcasts for premium users
        await self.generate_and_cache_podcasts_for_premium_users(classified_news)

        # 4) Retention cleanup
        await self._run_data_retention_cleanup()

        total_pipeline_time = time.time() - pipeline_start_time
        print(
            f"\n🏁 NEW Full Daily Pipeline Run Completed in {total_pipeline_time:.1f}s"
        )


# ---------------------------
# CLI entry point
# ---------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the News Processing Pipeline")
    parser.add_argument(
        "--mode",
        choices=["background", "test-api"],
        default="background",
        help="Run mode: 'background' for full daily job, 'test-api' for single user test",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        help="User ID for test-api mode",
    )

    args = parser.parse_args()

    pipeline = NewsProcessingPipeline(max_workers=3)

    if args.mode == "background":
        print("\n--- Initiating Full Asynchronous Background Pipeline Run ---")
        asyncio.run(pipeline.run_full_daily_pipeline())
        print("--- Full Asynchronous Background Pipeline Run Finished ---")

    elif args.mode == "test-api":
        print("\n--- Initiating Test API Call ---")
        if not args.user_id:
            print("Error: --user-id is required for test-api mode.")
            sys.exit(1)

        async def test_api_call() -> None:
            sample_user_prefs = {
                "user_id": args.user_id,  # Expected to be a real DB user ID
                "email": f"user{args.user_id}@example.com",
            }
            result = await pipeline.process_daily_news(sample_user_prefs)
            if "top_7" in result and result["top_7"]:
                print(f"\n--- Test API Result for User {args.user_id} ---")
                for i, article in enumerate(result["top_7"]):
                    print(f"\n--- Article {i+1} ---")
                    print(f"📰 Title: {article.get('title')}")
                    print(f"🔗 URL: {article.get('url')}")
                    print(f"🏷️  Category: {article.get('category')}")
                    print(f"📊 Relevance Score: {article.get('relevance_score', 'N/A')}")
                    print(
                        f"📈 Importance Score: {article.get('importance_score', 'N/A')}"
                    )
                    ynk = article.get("ynk_summary", "N/A")
                    print(f"💡 YNK Summary: {ynk}")

                # TEMP: treat even IDs as premium for demo
                is_premium_user = args.user_id % 2 == 0

                if is_premium_user:
                    print(
                        "\n🎙️  🎧  Generating personalized podcast for PREMIUM user...  🎧  🎙️"
                    )
                    try:
                        # Use helper to support sync or async podcast generators
                        maybe_result = (
                            pipeline.podcast_generator.generate_podcast_script(
                                {
                                    "user_id": args.user_id,
                                    "email": f"user{args.user_id}@example.com",
                                },
                                result["top_7"],
                            )
                        )
                        podcast = await pipeline._maybe_await(maybe_result)
                        if podcast:
                            print(
                                f"\n--- 🎙️  Personalized Podcast Script for User {args.user_id} ---"
                            )
                            print(podcast)
                            print("\n--- 🎧 End of Podcast Script ---")
                        else:
                            print(
                                f"\n⚠️  Podcast script could not be generated for user {args.user_id}."
                            )
                    except Exception as e:
                        print(
                            f"\n❌ Error generating podcast for user {args.user_id}: {e}"
                        )
                else:
                    print(
                        f"\nℹ️  User {args.user_id} is not a premium user. Podcast generation skipped."
                    )
            else:
                print(f"\n--- Test API Result for User {args.user_id} ---")
                print("No cached news found or error occurred.")
                print(result)

        asyncio.run(test_api_call())
        print("--- Test API Call Finished ---")
