# src/news_pipeline.py
"""Complete news processing pipeline with real user integration, feedback, and data retention."""

import asyncio
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Set, Union


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

# Import database session for data retention
try:
    from database import engine, get_db_session

    DATABASE_AVAILABLE = True
    print("✅ Imported database successfully")
except ImportError as e:
    print(f"⚠️ Database module not fully available for data retention: {e}")
    get_db_session = None
    engine = None
    DATABASE_AVAILABLE = False


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
        self.processed_news_count = 0
        self.total_processing_time = 0.0
        print("🚀 NewsProcessingPipeline initialized with enhanced SmartNewsFetcher")

    def get_all_users(self) -> List[Any]:
        """Get all registered users from the system."""
        users = []
        for user_id in USER_PROFILES.keys():
            user = get_user_profile(user_id)
            if user:
                users.append(user)
        print(f"👥 Loaded {len(users)} users from system")
        return users

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
        self, news_bundle: Dict[str, List[Dict]], user_profile: Union[Dict, Any]
    ) -> List[Dict]:
        """
        Selects the TOP-7 articles for a specific user from the news_bundle.
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
            for articles_in_category in news_bundle.values():
                for article in articles_in_category:
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

            category_articles = news_bundle.get(category, [])
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
                    a for cat_articles in news_bundle.values() for a in cat_articles
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
        if not DATA_RETENTION_ENABLED or not DATABASE_AVAILABLE or not engine:
            print(
                "⚠️ Data retention is disabled or database is not configured. Skipping cleanup."
            )
            return

        print("--- Initiating Automatic Data Retention Cleanup ---")
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

            async with AsyncSessionFactory() as session:
                # Call the function from data_retention.py
                deleted_counts = await perform_data_retention_cleanup(session)
                print("--- Data Retention Cleanup Summary ---")
                for task, count in deleted_counts.items():
                    print(f"  ✅ {task}: {count} items")
                print("--------------------------------------")
        except Exception as e:
            print(f"⚠️ Data retention cleanup failed: {e}")

    def process_daily_news(
        self, user_preferences: Union[Dict, Any]
    ) -> Dict[str, List[Dict]]:
        """
        Process daily news batch for a user.
        NOTE: This is a SYNCHRONOUS method, not async!

        Args:
            user_preferences: User profile (object or dict) with locale, interests, language preferences

        Returns:
            Dictionary containing the 'top_7' articles
        """
        # Ensure user_preferences is a dict for internal use
        user_prefs_dict = self._convert_user_profile_to_dict(user_preferences)

        user_id = user_prefs_dict.get("user_id", "Unknown")
        user_locale = user_prefs_dict.get("locale", "US")
        user_language = user_prefs_dict.get("language", "en")
        user_city = user_prefs_dict.get("city", "")
        user_interests = user_prefs_dict.get("interests", [])

        print(f"\n📡 Fetching global news bundle for user preferences:")
        print(f"   🌍 Locale: {user_locale} | 🗣️  Language: {user_language}")
        print(f"   🎯 Interests: {user_interests} | 🏙️  City: {user_city}")

        start_time = time.time()

        # Get all users (for context, though we process for one)
        users = self.get_all_users()

        # Process news using enhanced fetcher
        # Pass the dict version of user preferences
        news_bundle = self.fetcher.fetch_daily_news_bundle(user_prefs_dict)

        end_time = time.time()
        processing_time = end_time - start_time

        self.processed_news_count += sum(
            len(articles) for articles in news_bundle.values()
        )
        self.total_processing_time += processing_time

        print(
            f"\n🎯 PERSONALIZED TOP-7 FOR USER: {user_id} (Processed in {processing_time:.1f}s)"
        )

        # Select TOP-7 articles for the user
        # Pass the dict version of user preferences
        top_7_articles = self._select_top_articles_for_user(
            news_bundle, user_prefs_dict
        )

        # Group articles by category for ordered display
        articles_by_category = defaultdict(list)
        for article in top_7_articles:
            category = article.get("category", "general")
            articles_by_category[category].append(article)

        # Order categories by user preference
        user_id_for_sorting = user_prefs_dict.get("user_id")
        ordered_categories = []
        if self.feedback_system:
            categories_in_top7 = list(articles_by_category.keys())
            ordered_categories = sorted(
                categories_in_top7,
                key=lambda cat: self.feedback_system.get_user_preference(
                    user_id_for_sorting, cat
                ),
                reverse=True,
            )
        else:
            # Fallback order based on profile interests
            user_interests_from_profile = user_prefs_dict.get("interests", [])
            main_interests_from_profile = [
                i for i in user_interests_from_profile if isinstance(i, str)
            ]
            main_interests_from_profile.extend(
                [
                    list(i.keys())[0]
                    for i in user_interests_from_profile
                    if isinstance(i, dict)
                ]
            )

            for interest in main_interests_from_profile:
                if (
                    interest in articles_by_category
                    and interest not in ordered_categories
                ):
                    ordered_categories.append(interest)
            for cat in articles_by_category:
                if cat not in ordered_categories:
                    ordered_categories.append(cat)

        # Display articles, grouped and ordered by category
        article_counter = 1
        for category in ordered_categories:
            category_articles = articles_by_category[category]
            category_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )

            for article in category_articles:
                print(
                    f"\n--- Article {article_counter} (Category: {category.upper()}) ---"
                )
                print(f"📰 Title: {article.get('title')}")
                print(f"🔗 Source: {article.get('source')}")
                print(f"📊 Relevance Score: {article.get('relevance_score', 0):.2f}")
                print(f"🏷️  Category: {article.get('category')}")
                print(
                    f"🧠 AI Confidence: {article.get('confidence', 0):.2f} | Importance: {article.get('importance_score', 0)}/100"
                )
                if "contextual_factors" in article:
                    ctx = article["contextual_factors"]
                    print(
                        f"🔍 Context: Global {ctx.get('global_impact', 'N/A')}, Time {ctx.get('time_sensitivity', 'N/A')}"
                    )

                # Generate and display YNK (now with correct format and language)
                ynk_summary = self._generate_ynk_summary(article)
                print(f"💡 Why Not Care (YNK) Summary:\n{ynk_summary}")
                # Add the summary to the article object for potential later use
                article["ynk_summary"] = ynk_summary
                article_counter += 1

        return {"top_7": top_7_articles}

    async def run_full_daily_pipeline(self):
        """
        Runs the complete daily pipeline: fetch, process, deliver, and cleanup.
        This is the main orchestrator.
        """
        print("🚀 Starting Full Daily News Pipeline Run...")
        pipeline_start_time = time.time()

        # --- 1. Fetch and Process for All Users ---
        users = self.get_all_users()
        if not users:
            print("⚠️ No users found. Exiting pipeline.")
            return

        for user in users:
            # Safely get user_id
            if isinstance(user, dict):
                user_id = user.get("user_id", "Unknown")
            else:
                user_id = getattr(user, "user_id", "Unknown")
            print(f"\n--- Processing for User: {user_id} ---")

            # Process and display for each user
            # The conversion to dict is handled inside process_daily_news now
            _ = self.process_daily_news(user)

        # --- 2. Run Data Retention Cleanup ---
        await self._run_data_retention_cleanup()

        # --- 3. Finalize ---
        total_pipeline_time = time.time() - pipeline_start_time
        print(f"\n🏁 Full Daily Pipeline Run Completed in {total_pipeline_time:.1f}s")


# Test execution for MVP
if __name__ == "__main__":
    # Initialize pipeline
    pipeline = NewsProcessingPipeline(max_workers=3)

    # Test with sample user preferences (like your Maxonchik profile)
    # Using a dict directly for simplicity in this test
    sample_preferences = {
        "user_id": "Maxonchik",
        "locale": "DE",
        "language": "en",
        "city": "Frankfurt",
        "interests": [
            "economy_finance",
            "technology_ai_science",
            "politics_geopolitics",
            {
                "sports": [
                    "basketball_nba",
                    "football_epl",
                    "formula1",
                    "football_bundesliga",
                ]
            },
        ],
    }

    print("\n--- Initiating Full Asynchronous Pipeline Run ---")
    # Process daily news (SYNCHRONOUS CALL inside the ASYNC pipeline runner!)
    result = pipeline.process_daily_news(sample_preferences)
    top_7_articles = result.get("top_7", [])

    # The final output is already inside process_daily_news, so we can just finish here
    # Or print an additional summary, if needed
    # print(f"\n🏁 Pipeline execution completed. Top 7 articles selected for {sample_preferences['user_id']}.") # Minimize logs

    # Run the async cleanup part
    asyncio.run(pipeline._run_data_retention_cleanup())
    print("--- Full Asynchronous Pipeline Run Finished ---")
