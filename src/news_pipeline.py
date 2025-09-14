# src/news_pipeline.py
"""Complete news processing pipeline with real user integration and feedback."""

import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Set


def setup_paths():
    """Setup paths for correct imports."""
    current_dir = os.path.dirname(__file__)
    root_dir = os.path.dirname(current_dir)
    paths_to_add = [root_dir, current_dir]
    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)


setup_paths()

# Import our modules
try:
    from news_fetcher import SmartNewsFetcher
except ImportError as e:
    print(f"❌ Failed to import SmartNewsFetcher: {e}")
    sys.exit(1)

try:
    from user_profile import USER_PROFILES, get_user_profile
except ImportError as e:
    print(f"❌ Failed to import user_profile: {e}")
    sys.exit(1)

try:
    from cache_manager import get_cache_manager
except ImportError as e:
    print(f"❌ Failed to import cache_manager: {e}")
    sys.exit(1)

try:
    from summarizer import summarize_news
except ImportError as e:
    print(f"❌ Failed to import summarizer: {e}")
    summarize_news = None

try:
    from feedback_system import feedback_system
except ImportError as e:
    print(f"❌ Failed to import feedback_system: {e}")
    feedback_system = None


class NewsProcessingPipeline:
    """Orchestrates the complete news processing workflow for personalized delivery."""

    def __init__(self, max_workers: int = 5):
        """
        Initialize the complete news processing pipeline.

        Args:
            max_workers: Maximum number of concurrent tasks
        """
        self.max_workers = max_workers
        self.fetcher = SmartNewsFetcher()
        self.cache = get_cache_manager()
        self.feedback_system = feedback_system
        self.summarize_news_func = summarize_news
        self.processed_news_count = 0
        self.total_processing_time = 0.0

    def get_all_users(self) -> List[Any]:
        users = []
        for user_id in USER_PROFILES.keys():
            user = get_user_profile(user_id)
            if user:
                users.append(user)
        return users

    def _generate_ynk_summary(self, article: Dict) -> str:
        """Generates a YNK (Why Not Care) summary for an article."""
        if not self.summarize_news_func:
            return "Summary module not available."
        try:
            news_text = (
                article.get("content", "")
                or article.get("description", "")
                or article.get("title", "")
            )
            if not news_text.strip():
                return "No content available."
            category = article.get("category", "general")
            return self.summarize_news_func(news_text, category)
        except Exception as e:
            return f"Summary generation failed. Error: {e}"

    def _select_top_articles_for_user(
        self, news_bundle: Dict[str, List[Dict]], user_profile: Dict
    ) -> List[Dict]:
        """
        Selects TOP-7 articles, prioritizing user's specific interests.
        Guarantees representation from specific subcategories if possible,
        then from main categories, then fills with top remaining articles.
        """
        selected_articles = []
        seen_titles: Set[str] = set()
        user_id = user_profile.get("user_id", "unknown_user")

        user_interests = user_profile.get("interests", [])

        # 1. Extract specific subcategories (e.g., football_epl, formula1)
        specific_subcategories = set()
        for interest in user_interests:
            if isinstance(interest, dict):
                for subcats in interest.values():  # e.g., value for 'sports' key
                    if isinstance(subcats, list):
                        specific_subcategories.update(subcats)

        # 2. Extract main categories (e.g., technology_ai_science, economy_finance)
        main_categories = set(
            interest for interest in user_interests if isinstance(interest, str)
        )

        # --- Selection Logic ---
        # a. Try to guarantee articles for each specific subcategory
        # Sort subcategories by potential preference (feedback or profile order)
        sorted_specific_subcats = list(specific_subcategories)
        if self.feedback_system:
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

            # Sort by relevance and pick the best unique one
            matching_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )
            for article in matching_articles:
                title_key = article.get("title", "").lower()
                if title_key not in seen_titles and len(selected_articles) < 7:
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    # Mark the parent category as satisfied if it's in main_categories
                    # This is a heuristic: if user likes 'football_epl', they implicitly like 'sports'
                    # We can refine this logic later.
                    # For now, we don't block selecting a main category article later if needed.
                    break  # Take only the first match for this subcategory

        # b. Guarantee articles for main categories (that don't have specific subcats defined or weren't satisfied)
        # Sort main categories by potential preference
        sorted_main_cats = list(main_categories)
        if self.feedback_system:
            sorted_main_cats.sort(
                key=lambda cat: self.feedback_system.get_user_preference(user_id, cat),
                reverse=True,
            )

        for category in sorted_main_cats:
            # Only add if we haven't filled the quota
            if len(selected_articles) >= 7:
                break

            category_articles = news_bundle.get(category, [])
            category_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )

            for article in category_articles:
                title_key = article.get("title", "").lower()
                if title_key not in seen_titles and len(selected_articles) < 7:
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    break  # Take only the first match for this main category

        # c. Fill remaining slots with the best articles overall
        if len(selected_articles) < 7:
            all_articles_sorted = sorted(
                [a for articles in news_bundle.values() for a in articles],
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

        return selected_articles

    def process_daily_news(self, user_preferences: Dict) -> Dict[str, List[Dict]]:
        start_time = time.time()
        news_bundle = self.fetcher.fetch_daily_news_bundle(user_preferences)
        processing_time = time.time() - start_time

        self.processed_news_count += sum(
            len(articles) for articles in news_bundle.values()
        )
        self.total_processing_time += processing_time

        print(
            f"\n🎯 PERSONALIZED TOP-7 FOR USER: {user_preferences.get('user_id', 'Unknown')} (Processed in {processing_time:.1f}s)"
        )

        top_7_articles = self._select_top_articles_for_user(
            news_bundle, user_preferences
        )

        # Group by category for display
        articles_by_category = defaultdict(list)
        for article in top_7_articles:
            category = article.get("category", "general")
            articles_by_category[category].append(article)

        # Order categories by user preference
        user_id = user_preferences.get("user_id")
        ordered_categories = []
        if self.feedback_system:
            categories_in_top7 = list(articles_by_category.keys())
            ordered_categories = sorted(
                categories_in_top7,
                key=lambda cat: self.feedback_system.get_user_preference(user_id, cat),
                reverse=True,
            )
        else:
            # Fallback order based on profile interests
            user_interests = user_preferences.get("interests", [])
            main_interests_from_profile = [
                i for i in user_interests if isinstance(i, str)
            ]
            main_interests_from_profile.extend(
                [list(i.keys())[0] for i in user_interests if isinstance(i, dict)]
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

        # Display articles
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

                # --- Добавляем дату публикации ---
                pub_date_raw = article.get("published_at")
                if pub_date_raw:
                    # Пытаемся красиво отформатировать дату, если она в стандартном формате
                    try:
                        # Обрабатываем основные форматы, включая RFC2822 и ISO
                        from email.utils import parsedate_to_datetime

                        import dateutil.parser  # type: ignore

                        if isinstance(pub_date_raw, str):
                            # Пробуем email.utils.parsedate_to_datetime (для RFC2822)
                            if " " in pub_date_raw and ":" in pub_date_raw:
                                dt_obj = parsedate_to_datetime(pub_date_raw)
                            else:
                                # Пробуем dateutil.parser (для ISO и других)
                                dt_obj = (
                                    dateutil.parser.isoparse(pub_date_raw)
                                    if pub_date_raw.endswith("Z")
                                    or "+" in pub_date_raw
                                    or "T" in pub_date_raw
                                    else dateutil.parser.parse(pub_date_raw)
                                )

                            formatted_pub_date = dt_obj.strftime("%Y-%m-%d %H:%M")
                            print(f"🕒 Published: {formatted_pub_date}")
                        else:
                            print(
                                f"🕒 Published: {pub_date_raw}"
                            )  # Если это уже объект datetime
                    except Exception:
                        # Если не удалось распарсить, выводим как есть
                        print(f"🕒 Published: {pub_date_raw}")
                # --- Конец добавления даты ---

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

                ynk_summary = self._generate_ynk_summary(article)
                print(f"💡 Why Not Care (YNK) Summary:\n{ynk_summary}")
                article["ynk_summary"] = ynk_summary
                article_counter += 1

        return {"top_7": top_7_articles}


if __name__ == "__main__":
    pipeline = NewsProcessingPipeline(max_workers=3)

    sample_preferences = {
        "user_id": "Max",
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

    result = pipeline.process_daily_news(sample_preferences)
    # Result is printed inside process_daily_news
