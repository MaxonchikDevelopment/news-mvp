# src/news_pipeline.py
"""Complete news processing pipeline with real user integration, feedback, and data retention.
Implements NEW optimized architecture:
1. Background task fetches/classifies/generates YNK for ALL news ONCE and saves to DB (news_items).
2. Background task generates personalized TOP-7 for ALL users ONCE from pre-processed news and caches it (user_news_cache).
3. Background task generates personalized podcast scripts for PREMIUM users ONCE and caches it (user_news_cache).
4. API endpoint only reads pre-built bundle from cache for instant response.
"""

import asyncio
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union


# --- Path setup for internal imports ---
def setup_paths():
    """Setup paths for correct imports."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    paths_to_add = [project_root, current_dir]
    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)


setup_paths()

# Import our modules
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
    summarize_news = None

try:
    from feedback_system import feedback_system

    print("✅ Imported feedback_system successfully")
except ImportError as e:
    print(f"❌ Failed to import feedback_system: {e}")
    feedback_system = None

# --- Import Data Retention Module ---
try:
    from data_retention import perform_data_retention_cleanup

    DATA_RETENTION_ENABLED = True
    print("✅ Imported data_retention successfully")
except ImportError as e:
    print(f"⚠️ Data retention module not available: {e}. Cleanup will be skipped.")
    perform_data_retention_cleanup = None
    DATA_RETENTION_ENABLED = False

# Import database session and models for saving news items and caching bundles
try:
    from sqlalchemy import delete, select

    from database import AsyncSessionFactory  # Correct import
    from models import NewsItem
    from models import User as DBUser  # SQLAlchemy models
    from models import UserNewsCache
    from models import UserProfile as DBUserProfile

    DATABASE_AVAILABLE = True
    print("✅ Imported database and models successfully")
except ImportError as e:
    print(f"⚠️ Database or models not fully available for saving news items: {e}")
    AsyncSessionFactory = None
    NewsItem = None
    DBUser = None
    DBUserProfile = None
    UserNewsCache = None
    select = None
    delete = None
    DATABASE_AVAILABLE = False

# --- Import Podcast Generator ---
try:
    from src.podcast_generator import get_podcast_generator  # <-- Импорт

    PODCAST_GENERATOR_AVAILABLE = True
    print("✅ Imported podcast_generator successfully")
except ImportError as e:
    print(f"⚠️ Podcast generator module not available: {e}. Podcasts will be skipped.")
    get_podcast_generator = None
    PODCAST_GENERATOR_AVAILABLE = False


class NewsProcessingPipeline:
    """Orchestrates the complete news processing workflow for personalized delivery."""

    def __init__(self, max_workers: int = 5):
        """
        Initialize the complete news processing pipeline.

        Args:
            max_workers: Maximum number of concurrent tasks
        """
        self.max_workers = max_workers
        self.fetcher = SmartNewsFetcher()  # Use the enhanced fetcher
        self.cache = get_cache_manager()
        self.feedback_system = feedback_system
        self.summarize_news_func = summarize_news  # Store the summarizer function
        self.podcast_generator = get_podcast_generator()  # <-- Инициализация
        self.processed_news_count = 0
        self.total_processing_time = 0.0
        print(
            "🚀 NewsProcessingPipeline initialized with enhanced SmartNewsFetcher and PodcastGenerator"
        )

    def get_all_users(self) -> List[Any]:
        """Get all registered users from the system."""
        users = []
        for user_id in USER_PROFILES.keys():
            user = get_user_profile(user_id)
            if user:
                users.append(user)
        print(f"👥 Loaded {len(users)} users from system")
        return users

    async def get_all_users_from_db(self) -> List[Dict[str, Any]]:
        """Get all registered users from the database."""
        if (
            not DATABASE_AVAILABLE
            or not AsyncSessionFactory
            or not DBUser
            or not DBUserProfile
        ):
            print(
                "⚠️ Database not configured for fetching users. Returning system users."
            )
            # Fallback to system users if DB is not available
            system_users = self.get_all_users()
            db_user_list = []
            for user in system_users:
                user_dict = self._convert_user_profile_to_dict(user)
                db_user_list.append(
                    {
                        "id": user_dict.get("user_id"),
                        "email": f"{user_dict.get('user_id')}@example.com",  # Fallback email
                        "profile": user_dict,
                    }
                )
            return db_user_list

        async with AsyncSessionFactory() as db_session:
            try:
                # Join User and UserProfile
                stmt = select(DBUser, DBUserProfile).join(DBUserProfile, isouter=True)
                result = await db_session.execute(stmt)
                db_users_with_profiles = result.all()

                users_list = []
                for db_user, db_profile in db_users_with_profiles:
                    user_data = {
                        "id": db_user.id,
                        "email": db_user.email,
                        "profile": {
                            "user_id": db_user.id,
                            "locale": db_profile.locale if db_profile else "US",
                            "language": "en",  # Default or from profile
                            "city": None,  # Not stored
                            "interests": db_profile.interests if db_profile else [],
                        }
                        if db_profile
                        else None,
                    }
                    users_list.append(user_data)

                print(f"👥 Loaded {len(users_list)} users from database")
                return users_list
            except Exception as e:
                print(f"⚠️ Error fetching users from DB: {e}")
                return []

    def _convert_user_profile_to_dict(self, user_profile: Any) -> Dict[str, Any]:
        """
        Converts a user profile (object or dict) to a standard dictionary.
        Ensures compatibility with functions expecting a dict.
        """
        if isinstance(user_profile, dict):
            return user_profile
        elif hasattr(user_profile, "__dict__"):
            return user_profile.__dict__
        else:
            # Fallback for unexpected types (e.g., SimpleNamespace)
            print(
                f"⚠️ Unexpected user profile type: {type(user_profile)}. Attempting attribute access."
            )
            try:
                return {
                    "user_id": getattr(user_profile, "user_id", "unknown"),
                    "locale": getattr(user_profile, "locale", "US"),
                    "language": getattr(user_profile, "language", "en"),
                    "city": getattr(user_profile, "city", ""),
                    "interests": getattr(user_profile, "interests", []),
                }
            except Exception as e:
                print(f"❌ Failed to convert user profile to dict: {e}")
                return {}

    async def _save_news_items_to_db(self, news_bundle: dict):
        """Сохраняет уникальные новости из news_bundle в БД и обновляет их id."""
        if not DATABASE_AVAILABLE or not AsyncSessionFactory or not NewsItem:
            print("⚠️ Database not configured for saving news items. Skipping.")
            return

        # Собираем все уникальные статьи из news_bundle
        all_articles = []
        for category_articles in news_bundle.values():
            if isinstance(category_articles, list):
                all_articles.extend(category_articles)

        # Собираем уникальные URL'ы для проверки дедупликации
        unique_urls = set()
        articles_to_process = []
        for article in all_articles:
            url = article.get("url")
            if url and url not in unique_urls:
                unique_urls.add(url)
                articles_to_process.append(article)

        # Создаем временную сессию для сохранения новостей
        async with AsyncSessionFactory() as db_session:
            try:
                for article in articles_to_process:
                    # Пытаемся найти существующую новость по URL
                    stmt = select(NewsItem).where(NewsItem.url == article["url"])
                    result = await db_session.execute(stmt)
                    existing_item = result.scalar_one_or_none()

                    if existing_item:
                        # Новость уже есть, используем её ID
                        article["id"] = existing_item.id

                        # --- КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Гарантированное обновление ai_analysis ---
                        # Проверяем, нужно ли обновить ai_analysis
                        # Условие: ai_analysis отсутствует, не является словарем или не содержит ключей
                        needs_ai_update = (
                            not existing_item.ai_analysis
                            or not isinstance(existing_item.ai_analysis, dict)
                            or "ynk_summary" not in existing_item.ai_analysis
                            or not existing_item.ai_analysis.get("ynk_summary")
                            or "relevance_score" not in existing_item.ai_analysis
                            or "confidence" not in existing_item.ai_analysis
                        )

                        if needs_ai_update:
                            print(
                                f"  🔄 Updating incomplete ai_analysis for existing item ID {existing_item.id}..."
                            )

                            # Убедимся, что article содержит все необходимые данные
                            # Генерируем YNK, если его нет в article
                            if (
                                "ynk_summary" not in article
                                or not article["ynk_summary"]
                            ):
                                ynk_summary = self._generate_ynk_summary(article)
                                article["ynk_summary"] = ynk_summary
                            else:
                                ynk_summary = article["ynk_summary"]

                            # Убедимся, что article содержит scores (они обычно приходят из fetcher/classifier)
                            relevance_score = article.get("relevance_score", 0)
                            confidence = article.get("confidence", 0)

                            # Обновляем объект SQLAlchemy
                            existing_item.ai_analysis = {
                                "relevance_score": relevance_score,
                                "confidence": confidence,
                                "ynk_summary": ynk_summary,
                            }

                            # Добавляем в сессию для коммита
                            db_session.add(existing_item)
                            await db_session.commit()
                            await db_session.refresh(existing_item)
                            print(
                                f"  ✅ Updated ai_analysis for item ID {existing_item.id}."
                            )
                        # --- КОНЕЦ КРИТИЧЕСКОГО ИСПРАВЛЕНИЯ ---

                    else:
                        # Создаем новую новость
                        # --- ИСПРАВЛЕНИЕ: Обеспечить, что external_id не None ---
                        external_id_from_article = article.get(
                            "external_id"
                        )  # Может быть None
                        external_id_to_use = (
                            external_id_from_article
                            if external_id_from_article is not None
                            else article["url"]
                        )

                        # --- ИСПРАВЛЕНИЕ 1: Убедиться, что YNK уже сгенерирован и сохранен в article ---
                        # Проверим, есть ли YNK в article. Если нет, сгенерируем.
                        # Это важно, если _save_news_items_to_db вызывается не из fetch_and_classify_all_news напрямую.
                        if "ynk_summary" not in article or not article["ynk_summary"]:
                            ynk_summary = self._generate_ynk_summary(article)
                            article[
                                "ynk_summary"
                            ] = ynk_summary  # Сохраняем в article для последующего использования
                        else:
                            ynk_summary = article[
                                "ynk_summary"
                            ]  # Берем уже сгенерированный

                        new_item = NewsItem(
                            external_id=external_id_to_use,  # <-- ИСПРАВЛЕНО
                            source_name=article.get(
                                "source_name", article.get("source", "Unknown")
                            ),
                            title=article["title"],
                            url=article["url"],
                            category=article.get("category", "unknown"),
                            subcategory=article.get("subcategory"),  # Может быть None
                            importance_score=article.get("importance_score", 0),
                            ai_analysis={
                                "relevance_score": article.get("relevance_score", 0),
                                "confidence": article.get("confidence", 0),
                                # Добавляем YNK в ai_analysis для хранения в БД
                                "ynk_summary": ynk_summary,
                            },
                            fetched_at=datetime.utcnow(),
                            # ynk_summary будет храниться в ai_analysis, как указано выше.
                        )
                        # Удалена дублирующая запись ynk_summary в ai_analysis, она уже там выше.

                        db_session.add(new_item)
                        await db_session.commit()  # Сохраняем
                        await db_session.refresh(new_item)  # Получаем ID
                        article["id"] = new_item.id
                        # print(f"Created new news item: {new_item.id}") # Для отладки

                print(
                    f"✅ Saved/Checked {len(articles_to_process)} unique news items to DB."
                )
            except Exception as e:
                print(f"⚠️ Error saving news items to DB: {e}")
                await db_session.rollback()
                # Можно выбросить ошибку или продолжить (осторожно!)
                # raise

    def _generate_ynk_summary(self, article: Dict) -> str:
        """Generates a YNK (Why Not Care) summary for an article."""
        if not self.summarize_news_func:
            return "Summary generation module (summarizer.py) not available."

        try:
            # Use content, description, or title
            news_text = (
                article.get("content", "")
                or article.get("description", "")
                or article.get("title", "")
            )
            if not news_text.strip():
                return "No content, description, or title available for summary."

            # Use the AI-classified category to select the correct impact aspects
            category = article.get("category", "general")

            # Call summarize_news from summarizer.py
            summary = self.summarize_news_func(news_text, category)
            return summary
        except Exception as e:
            # print(f"⚠️ YNK summary generation failed for '{article.get('title', 'Unknown')}': {e}") # Minimize logs
            return f"Could not generate summary. Error: {e}"

    def _select_top_articles_for_user(
        self, classified_news_list: List[Dict], user_profile: Union[Dict, Any]
    ) -> List[Dict]:
        """
        Selects the TOP-7 articles for a specific user from the ALREADY CLASSIFIED news list.
        Guarantees representation from specific subcategories IF their relevance is high enough.
        Otherwise, fills TOP-7 with the best overall articles.
        """
        # --- CRITICAL FIX: Convert user_profile to dict ---
        user_profile_dict = self._convert_user_profile_to_dict(user_profile)
        # --- END FIX ---

        selected_articles = []
        seen_titles: Set[str] = set()  # For deduplication within TOP-7

        user_interests = user_profile_dict.get("interests", [])

        # --- Improved Interest Extraction Logic ---
        # 1. Extract main categories (e.g., 'economy_finance', 'technology_ai_science')
        main_categories = [
            interest for interest in user_interests if isinstance(interest, str)
        ]

        # 2. Extract specific subcategories (e.g., 'basketball_nba', 'football_epl')
        specific_subcategories: Set[str] = set()
        for interest in user_interests:
            if isinstance(interest, dict):
                for main_cat, subcats in interest.items():
                    if isinstance(subcats, list):
                        specific_subcategories.update(subcats)

        # --- Selection Logic with Minimum Relevance Threshold ---
        MIN_RELEVANCE_THRESHOLD = 0.40  # Articles below this won't be forced in

        # 1. Try to guarantee articles for each specific subcategory IF they meet the threshold
        sorted_specific_subcats = list(specific_subcategories)
        if self.feedback_system:
            user_id = user_profile_dict.get("user_id", "unknown_user")
            sorted_specific_subcats.sort(
                key=lambda subcat: self.feedback_system.get_user_preference(
                    user_id, subcat
                ),
                reverse=True,
            )

        for subcategory in sorted_specific_subcats:
            # Find articles matching the specific subcategory field
            matching_articles = []
            for article in classified_news_list:  # <-- Используем classified_news_list
                # Check for subcategory fields like 'sports_subcategory', 'economy_subcategory'
                article_subcats = [
                    article.get("sports_subcategory"),
                    article.get("economy_subcategory"),
                    article.get("tech_subcategory")
                    # Add others if classifier provides them
                ]
                if subcategory in article_subcats:
                    matching_articles.append(article)

            # Sort by relevance and pick the best unique one that meets the threshold
            matching_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )
            article_added_for_this_subcat = False
            for article in matching_articles:
                title_key = article.get("title", "").lower()
                relevance = article.get("relevance_score", 0)
                if (
                    title_key not in seen_titles
                    and len(selected_articles) < 7
                    and not article_added_for_this_subcat
                    and relevance >= MIN_RELEVANCE_THRESHOLD
                ):  # <-- NEW CHECK
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    # print(f"📌 Guaranteed article for specific subcategory '{subcategory}' (Score: {relevance:.2f}): {article.get('title', 'No Title')[:50]}...") # Minimize logs
                    article_added_for_this_subcat = True  # Take only the first (best) unique article from this subcategory
                    break  # Break inner loop once we find a good match

        # 2. Guarantee articles for main categories (that don't have specific subcats defined or weren't satisfied) IF they meet threshold
        sorted_main_cats = list(main_categories)
        if self.feedback_system:
            user_id = user_profile_dict.get("user_id", "unknown_user")
            sorted_main_cats.sort(
                key=lambda cat: self.feedback_system.get_user_preference(user_id, cat),
                reverse=True,
            )

        for category in sorted_main_cats:
            # Only add if we haven't filled the quota AND article meets threshold
            if len(selected_articles) >= 7:
                break

            category_articles = [
                a for a in classified_news_list if a.get("category") == category
            ]  # <-- Используем classified_news_list
            category_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )

            article_added_for_this_cat = False
            for article in category_articles:
                title_key = article.get("title", "").lower()
                relevance = article.get("relevance_score", 0)
                if (
                    title_key not in seen_titles
                    and len(selected_articles) < 7
                    and not article_added_for_this_cat
                    and relevance >= MIN_RELEVANCE_THRESHOLD
                ):  # <-- NEW CHECK
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    # print(f"📌 Guaranteed article for main category '{category}' (Score: {relevance:.2f}): {article.get('title', 'No Title')[:50]}...") # Minimize logs
                    article_added_for_this_cat = True  # Take only the first (best) unique article from this main category
                    break  # Break inner loop once we find a good match

        # 3. Fill remaining slots with the BEST articles overall (no threshold for fillers)
        if len(selected_articles) < 7:
            all_articles_sorted = sorted(
                [
                    a
                    for cat_articles in classified_news_list.values()
                    for a in cat_articles
                ],  # Flatten all articles
                key=lambda x: x.get("relevance_score", 0),
                reverse=True,
            )
            for article in all_articles_sorted:
                if len(selected_articles) >= 7:
                    break
                title_key = article.get("title", "").lower()
                if title_key not in seen_titles:
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    # print(f"🔝 Added to TOP-7 (filler): {article.get('title', 'No Title')[:50]}... (Score: {article.get('relevance_score', 0):.2f})") # Minimize logs

        # Ensure maximum of 7 and sort by final relevance score for display
        final_selection = selected_articles[:7]
        final_selection.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        print(
            f"🎯 Final news bundle ready: {len(final_selection)} articles selected for TOP-7"
        )
        # Optional: Print breakdown by category
        # from collections import Counter
        # cats = [a.get('category', 'unknown').upper() for a in final_selection]
        # cat_counts = Counter(cats)
        # for cat, count in cat_counts.items():
        #     print(f"   {cat}: {count} articles")

        return final_selection

    async def _run_data_retention_cleanup(self):
        """Runs the data retention cleanup tasks asynchronously."""
        if (
            not DATA_RETENTION_ENABLED
            or not DATABASE_AVAILABLE
            or not AsyncSessionFactory
        ):
            print(
                "⚠️ Data retention is disabled or database is not configured. Skipping cleanup."
            )
            return

        print("--- Initiating Automatic Data Retention Cleanup ---")
        try:
            # Use the imported AsyncSessionFactory
            async with AsyncSessionFactory() as session:
                # Call the function from data_retention.py
                deleted_counts = await perform_data_retention_cleanup(session)
                print("--- Data Retention Cleanup Summary ---")
                for task, count in deleted_counts.items():
                    print(f"  ✅ {task}: {count} items")
                print("--------------------------------------")
        except Exception as e:
            print(f"⚠️ Data retention cleanup failed: {e}")

    # --- НОВЫЕ МЕТОДЫ ДЛЯ НОВОЙ АРХИТЕКТУРЫ ---

    async def fetch_and_classify_all_news(self) -> List[Dict]:
        """
        Фоновая задача 1: Собирает, классифицирует и сохраняет ВСЕ новости.
        Генерирует универсальный YNK для каждой уникальной новости.
        Возвращает список словарей с данными новостей (включая ID из БД).
        """
        print("\n--- [BACKGROUND TASK 1] Fetching and Classifying ALL News ---")

        # Используем фиктивный профиль для сбора "всего"
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
            ],  # Все категории для макс. охвата
        }

        start_time = time.time()
        print(f"📡 Fetching global news bundle for all categories...")

        # --- 1. Fetch all news ---
        news_bundle = self.fetcher.fetch_daily_news_bundle(dummy_profile)
        fetch_time = time.time() - start_time
        print(
            f"📦 Raw articles collected: {sum(len(arts) for arts in news_bundle.values())} (in {fetch_time:.2f}s)"
        )

        # --- 2. Save to DB (includes classification and YNK generation) ---
        await self._save_news_items_to_db(news_bundle)
        save_time = time.time() - start_time - fetch_time
        print(f"💾 News saved/classified/YNK'd to DB (in {save_time:.2f}s)")

        # --- 3. Fetch the saved news back with IDs ---
        # Это нужно, чтобы получить окончательный список новостей с ID для следующего шага
        if not DATABASE_AVAILABLE or not AsyncSessionFactory or not NewsItem:
            print("⚠️ Cannot fetch saved news from DB. Returning empty list.")
            return []

        async with AsyncSessionFactory() as db_session:
            try:
                # Получаем все новости, сохраненные за последние сутки (или за другое окно)
                yesterday = datetime.utcnow() - timedelta(days=1)
                stmt = select(NewsItem).where(NewsItem.fetched_at >= yesterday)
                result = await db_session.execute(stmt)
                saved_news_items = result.scalars().all()

                # Конвертируем SQLAlchemy модели в словари
                saved_news_list = []
                for item in saved_news_items:
                    item_dict = {
                        "id": item.id,
                        "external_id": item.external_id,
                        "source_name": item.source_name,
                        "title": item.title,
                        "url": item.url,
                        "category": item.category,
                        "subcategory": item.subcategory,
                        "importance_score": item.importance_score,
                        "ai_analysis": item.ai_analysis,  # Содержит relevance_score, confidence, ynk_summary
                        "fetched_at": item.fetched_at.isoformat()
                        if item.fetched_at
                        else None,
                    }
                    saved_news_list.append(item_dict)

                print(
                    f"📤 Fetched {len(saved_news_list)} classified news items with IDs from DB."
                )
                return saved_news_list
            except Exception as e:
                print(f"⚠️ Error fetching saved news from DB: {e}")
                return []

    async def generate_and_cache_bundles_for_all_users(
        self, classified_news_list: List[Dict]
    ):
        """
        Фоновая задача 2: Генерирует персонализированные ленты для ВСЕХ пользователей
        и сохраняет их в кэш (user_news_cache).
        ИСПОЛЬЗУЕТ уже обработанные данные из classified_news_list.

        Args:
            classified_news_list: Список словарей с данными новостей (включая ID и YNK).
        """
        print(
            "\n--- [BACKGROUND TASK 2] Generating Personalized Bundles for ALL Users ---"
        )

        if not classified_news_list:
            print("⚠️ No classified news provided. Skipping bundle generation.")
            return

        # Получаем всех пользователей из БД
        all_users = await self.get_all_users_from_db()

        if not all_users:
            print("⚠️ No users found in database. Skipping bundle generation.")
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

                    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Передаем classified_news_list напрямую ---
                    # Генерируем ТОП-7 для пользователя ИЗ УЖЕ ОБРАБОТАННЫХ новостей
                    top_7_articles = self._select_top_articles_for_user(
                        classified_news_list, user_profile
                    )
                    # --- КОНЕЦ КЛЮЧЕВОГО ИСПРАВЛЕНИЯ ---

                    # --- Подготавливаем данные для кэша ---
                    # news_bundle - это список ID новостей или самих данных новостей
                    # Для простоты сохраним сами данные новостей
                    # --- ВАЖНО: Убедиться, что все нужные данные на верхнем уровне ---
                    prepared_top_7 = []
                    for article in top_7_articles:
                        # Копируем основные данные статьи
                        prepared_article = article.copy()
                        # Получаем ai_analysis (если есть)
                        ai_analysis = article.get("ai_analysis", {})
                        # Переносим данные из ai_analysis на верхний уровень
                        prepared_article["relevance_score"] = ai_analysis.get(
                            "relevance_score",
                            prepared_article.get("relevance_score", 0),
                        )
                        prepared_article["confidence"] = ai_analysis.get(
                            "confidence", prepared_article.get("confidence", 0)
                        )
                        prepared_article["ynk_summary"] = ai_analysis.get(
                            "ynk_summary", prepared_article.get("ynk_summary", "N/A")
                        )
                        # Можно также перенести другие данные, если нужно

                        prepared_top_7.append(prepared_article)

                    cache_data = {
                        "generated_at": datetime.utcnow().isoformat(),
                        "top_7": prepared_top_7,  # Содержит ID, title, url, category, relevance_score, importance_score, ynk_summary
                    }

                    # Создаем или обновляем запись в кэше
                    stmt_check = select(UserNewsCache).where(
                        UserNewsCache.user_id == user_id,
                        UserNewsCache.news_date == today,
                    )
                    result = await db_session.execute(stmt_check)
                    existing_cache = result.scalar_one_or_none()

                    if existing_cache:
                        # Обновляем существующую запись
                        existing_cache.news_bundle = cache_data
                        existing_cache.generated_at = datetime.utcnow()
                        print(f"    🔄 Updated cache for user {user_email}.")
                    else:
                        # Создаем новую запись
                        new_cache_entry = UserNewsCache(
                            user_id=user_id, news_date=today, news_bundle=cache_data
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
        self, classified_news_list: List[Dict]
    ):
        """
        Фоновая задача 3: Генерирует персонализированные подкасты для ВСЕХ ПРЕМИУМ пользователей
        и сохраняет их в кэш (user_news_cache).
        ИСПОЛЬЗУЕТ уже обработанные данные из classified_news_list.

        Args:
            classified_news_list: Список словарей с данными новостей (включая ID и YNK).
        """
        print(
            "\n--- [BACKGROUND TASK 3] Generating Personalized Podcasts for ALL Premium Users ---"
        )

        if not classified_news_list:
            print("⚠️ No classified news provided. Skipping podcast generation.")
            return

        if not PODCAST_GENERATOR_AVAILABLE or not self.podcast_generator:
            print("⚠️ Podcast generator is not available. Skipping podcast generation.")
            return

        # Получаем всех пользователей из БД
        all_users = await self.get_all_users_from_db()

        if not all_users:
            print("⚠️ No users found in database. Skipping podcast generation.")
            return

        # Фильтруем только премиум-пользователей
        # TODO: Заменить на реальную проверку статуса премиум-пользователя
        # Например: is_premium = await check_user_premium_status(user_id, db_session)
        # Пока используем фиктивную проверку: все пользователи с четным ID считаются премиум
        premium_users = [
            user for user in all_users if user["id"] % 2 == 0
        ]  # <-- ЗАГЛУШКА
        # premium_users = [user for user in all_users if user['id'] in [1, 2]] # <-- АЛЬТЕРНАТИВНАЯ ЗАГЛУШКА (пользователи 1 и 2)
        # premium_users = all_users # <-- ЗАГЛУШКА (все пользователи премиум)

        if not premium_users:
            print("⚠️ No premium users found in database. Skipping podcast generation.")
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

                    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Передаем classified_news_list напрямую ---
                    # Генерируем ТОП-7 для пользователя ИЗ УЖЕ ОБРАБОТАННЫХ новостей
                    top_7_articles = self._select_top_articles_for_user(
                        classified_news_list, user_profile
                    )
                    # --- КОНЕЦ КЛЮЧЕВОГО ИСПРАВЛЕНИЯ ---

                    # --- Подготавливаем данные для подкаста ---
                    # news_bundle - это список ID новостей или самих данных новостей
                    # Для простоты сохраним сами данные новостей
                    # --- ВАЖНО: Убедиться, что все нужные данные на верхнем уровне ---
                    prepared_top_7 = []
                    for article in top_7_articles:
                        # Копируем основные данные статьи
                        prepared_article = article.copy()
                        # Получаем ai_analysis (если есть)
                        ai_analysis = article.get("ai_analysis", {})
                        # Переносим данные из ai_analysis на верхний уровень
                        prepared_article["relevance_score"] = ai_analysis.get(
                            "relevance_score",
                            prepared_article.get("relevance_score", 0),
                        )
                        prepared_article["confidence"] = ai_analysis.get(
                            "confidence", prepared_article.get("confidence", 0)
                        )
                        prepared_article["ynk_summary"] = ai_analysis.get(
                            "ynk_summary", prepared_article.get("ynk_summary", "N/A")
                        )
                        # Можно также перенести другие данные, если нужно

                        prepared_top_7.append(prepared_article)

                    # --- Генерация подкаста ---
                    try:
                        print(
                            f"    🧠 Calling podcast generator for user {user_email}..."
                        )
                        podcast_script = (
                            await self.podcast_generator.generate_podcast_script(
                                user_profile, prepared_top_7
                            )
                        )
                        print(f"    ✅ Podcast script generated for user {user_email}.")
                    except Exception as e:
                        print(
                            f"    ⚠️ Error generating podcast script for user {user_email}: {e}"
                        )
                        podcast_script = "Sorry, the podcast script could not be generated at this time."
                    # --- КОНЕЦ Генерации подкаста ---

                    # --- Обновляем кэш с подкастом ---
                    stmt_check = select(UserNewsCache).where(
                        UserNewsCache.user_id == user_id,
                        UserNewsCache.news_date == today,
                    )
                    result = await db_session.execute(stmt_check)
                    existing_cache = result.scalar_one_or_none()

                    if existing_cache:
                        # Обновляем существующую запись
                        existing_cache.news_bundle["podcast_script"] = podcast_script
                        existing_cache.generated_at = datetime.utcnow()
                        print(
                            f"    🔄 Updated cache with podcast for user {user_email}."
                        )
                    else:
                        # Создаем новую запись с подкастом
                        cache_data = {
                            "generated_at": datetime.utcnow().isoformat(),
                            "top_7": prepared_top_7,  # Содержит ID, title, url, category, relevance_score, importance_score, ynk_summary
                            "podcast_script": podcast_script,
                        }
                        new_cache_entry = UserNewsCache(
                            user_id=user_id, news_date=today, news_bundle=cache_data
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

    async def get_cached_news_bundle_for_user(self, user_id: int) -> Optional[Dict]:
        """
        API-метод: Получает готовую персонализированную ленту пользователя из кэша.

        Args:
            user_id: ID пользователя в БД.

        Returns:
            Словарь с ключом 'top_7' и списком новостей, или None, если кэш не найден.
        """
        if not DATABASE_AVAILABLE or not AsyncSessionFactory or not UserNewsCache:
            print("⚠️ Database not configured for fetching cached news.")
            return None

        async with AsyncSessionFactory() as db_session:
            try:
                today = date.today()
                stmt = select(UserNewsCache).where(
                    UserNewsCache.user_id == user_id, UserNewsCache.news_date == today
                )
                result = await db_session.execute(stmt)
                cache_entry = result.scalar_one_or_none()

                if cache_entry:
                    print(f"✅ Found cached news bundle for user ID {user_id}.")
                    # news_bundle - это словарь, который мы сохранили
                    return cache_entry.news_bundle
                else:
                    print(
                        f"⚠️ No cached news bundle found for user ID {user_id} for {today}."
                    )
                    return None
            except Exception as e:
                print(f"⚠️ Error fetching cached news for user {user_id}: {e}")
                return None

    async def get_cached_podcast_script_for_user(self, user_id: int) -> Optional[Dict]:
        """
        API-метод: Получает готовый персонализированный подкаст пользователя из кэша.

        Args:
            user_id: ID пользователя в БД.

        Returns:
            Словарь с ключом 'script' и текстом подкаста, или None, если кэш не найден.
        """
        if not DATABASE_AVAILABLE or not AsyncSessionFactory or not UserNewsCache:
            print("⚠️ Database not configured for fetching cached podcast.")
            return None

        async with AsyncSessionFactory() as db_session:
            try:
                today = date.today()
                stmt = select(UserNewsCache).where(
                    UserNewsCache.user_id == user_id, UserNewsCache.news_date == today
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
        self, user_id: int, top_7_articles: List[Dict]
    ) -> Optional[Dict[str, str]]:
        """
        Generates a personalized podcast script for a user based on their TOP-7 articles.

        Args:
            user_id: The ID of the user in the database.
            top_7_articles: The list of 7 articles from the user's personalized feed.

        Returns:
            A dictionary with the key 'script' and the podcast text, or None on error.
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

        try:
            # Получаем профиль пользователя из БД
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
                    "language": "en",  # Default or from profile
                    "city": None,  # Not stored
                    "interests": db_profile.interests if db_profile else [],
                    "is_premium": db_profile.is_premium
                    if db_profile
                    else False,  # <-- Получаем is_premium
                }

            # Генерируем скрипт подкаста
            podcast_script = self.podcast_generator.generate_podcast_script(
                user_profile_data, top_7_articles
            )  # <-- await

            print(f"✅  Podcast script generated successfully for user ID {user_id}.")
            return {"script": podcast_script}

        except Exception as e:
            print(f"❌  Error generating podcast script for user {user_id}: {e}")
            return None

    # --- КОНЕЦ НОВОГО МЕТОДА ---

    # --- СТАРЫЙ МЕТОД process_daily_news (для совместимости или прямого вызова) ---
    # Он теперь будет использовать новый кэшированный подход, если вызывается из API
    async def process_daily_news(
        self, user_preferences: Union[Dict, Any]
    ) -> Dict[str, List[Dict]]:
        """
        Process daily news batch for a user.
        NOTE: This method is now primarily for API use and reads from cache.
        For background processing, use fetch_and_classify_all_news and generate_and_cache_bundles_for_all_users.

        Args:
            user_preferences: User profile (object or dict). Used to get user_id for cache lookup.

        Returns:
            Dictionary containing the 'top_7' articles from cache, or an error message.
        """
        # Ensure user_preferences is a dict for internal use
        user_prefs_dict = self._convert_user_profile_to_dict(user_preferences)
        user_id = user_prefs_dict.get("user_id")

        # Пытаемся получить user_id как int из БД (если это объект пользователя)
        # Это упрощенная логика, в реальном API user_id будет браться из токена
        db_user_id = None
        if isinstance(user_id, int):
            db_user_id = user_id
        elif isinstance(user_id, str) and user_id.isdigit():
            db_user_id = int(user_id)
        else:
            # Попробуем найти пользователя в БД по email из профиля
            email = user_prefs_dict.get("email") or f"{user_id}@example.com"  # fallback
            if DATABASE_AVAILABLE and AsyncSessionFactory and DBUser:
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
                f"⚠️ Could not determine database user ID for preferences {user_id}. Cannot fetch from cache."
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

    async def run_full_daily_pipeline(self):
        """
        Runs the NEW complete daily pipeline: fetch, classify, save, personalize, cache.
        This is the main orchestrator for the background task.
        """
        print("🚀 Starting NEW Full Daily News Pipeline Run (Background Task)...")
        pipeline_start_time = time.time()

        # --- 1. Fetch and classify all news ---
        classified_news = await self.fetch_and_classify_all_news()

        # --- 2. Generate and cache bundles for all users ---
        await self.generate_and_cache_bundles_for_all_users(classified_news)

        # --- 3. Generate and cache podcasts for premium users ---
        await self.generate_and_cache_podcasts_for_premium_users(classified_news)

        # --- 4. Run Data Retention Cleanup ---
        await self._run_data_retention_cleanup()

        # --- 5. Finalize ---
        total_pipeline_time = time.time() - pipeline_start_time
        print(
            f"\n🏁 NEW Full Daily Pipeline Run Completed in {total_pipeline_time:.1f}s"
        )


# --- Скрипт для ручного запуска фонового процесса ---
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the News Processing Pipeline")
    parser.add_argument(
        "--mode",
        choices=["background", "test-api"],
        default="background",
        help="Run mode: 'background' for full daily job, 'test-api' for single user test",
    )
    parser.add_argument("--user-id", type=int, help="User ID for test-api mode")

    args = parser.parse_args()

    # Initialize pipeline
    pipeline = NewsProcessingPipeline(max_workers=3)

    if args.mode == "background":
        print("\n--- Initiating Full Asynchronous Background Pipeline Run ---")
        # Run the NEW async pipeline
        asyncio.run(pipeline.run_full_daily_pipeline())
        print("--- Full Asynchronous Background Pipeline Run Finished ---")

    elif args.mode == "test-api":
        print("\n--- Initiating Test API Call ---")
        # For testing the API-like behavior (reads from cache)
        if not args.user_id:
            print("Error: --user-id is required for test-api mode.")
            sys.exit(1)

        async def test_api_call():
            sample_user_prefs = {
                "user_id": args.user_id,  # This should be a real DB user ID
                "email": f"user{args.user_id}@example.com",  # Fallback
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
                    print(f"💡 YNK Summary: {ynk}")  # Выводим полный текст

                # --- НОВОЕ: Автоматический вывод подкаста для премиум-пользователей ---
                # Проверим статус премиум у пользователя (через БД или временную заглушку)
                # Временная заглушка: все пользователи с четным ID - премиум
                # TODO: Заменить на реальную проверку из БД
                is_premium_user = args.user_id % 2 == 0  # <-- TEMPORARY FOR TESTING
                # is_premium_user = True # <-- ALTERNATIVE TEMPORARY FOR TESTING (все пользователи премиум)

                if is_premium_user:
                    print(f"\n🎙️  🎧  🎤  🎧  🎙️  🎧  🎤  🎧  🎙️  🎧  🎤  🎧")
                    print(
                        f"🎧  Generating personalized podcast for PREMIUM user {args.user_id}...  🎧"
                    )
                    print(f"🎙️  🎧  🎤  🎧  🎙️  🎧  🎤  🎧  🎙️  🎧  🎤  🎧")

                    try:
                        # Генерируем подкаст
                        podcast_result = (
                            await pipeline.generate_podcast_script_for_user(
                                args.user_id, result["top_7"]
                            )
                        )  # <-- await
                        if podcast_result and "script" in podcast_result:
                            print(
                                f"\n--- 🎙️  Personalized Podcast Script for User {args.user_id} ---"
                            )
                            print(
                                podcast_result["script"]
                            )  # Выводим полный текст подкаста
                            print(f"\n--- 🎧 End of Podcast Script ---")
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
                # --- КОНЕЦ НОВОГО ---
            else:
                print(f"\n--- Test API Result for User {args.user_id} ---")
                print("No cached news found or error occurred.")
                print(result)

        asyncio.run(test_api_call())
        print("--- Test API Call Finished ---")
