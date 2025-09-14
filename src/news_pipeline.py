# src/news_pipeline.py
"""Complete news processing pipeline with real user integration and feedback."""

import hashlib
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple


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

    # print("✅ Imported SmartNewsFetcher successfully") # Minimize logs
except ImportError as e:
    print(f"❌ Failed to import SmartNewsFetcher: {e}")
    sys.exit(1)

try:
    from user_profile import USER_PROFILES, get_user_profile

    # print("✅ Imported user_profile successfully") # Minimize logs
except ImportError as e:
    print(f"❌ Failed to import user_profile: {e}")
    sys.exit(1)

try:
    from cache_manager import get_cache_manager

    # print("✅ Imported cache_manager successfully") # Minimize logs
except ImportError as e:
    print(f"❌ Failed to import cache_manager: {e}")
    sys.exit(1)

try:
    # Import summarizer for YNK generation
    from summarizer import summarize_news

    # print("✅ Imported summarizer successfully") # Minimize logs
except ImportError as e:
    print(f"❌ Failed to import summarizer: {e}")
    summarize_news = None  # Fallback if summarizer is not available

try:
    from feedback_system import feedback_system

    # print("✅ Imported feedback_system successfully") # Minimize logs
except ImportError as e:
    print(f"❌ Failed to import feedback_system: {e}")
    feedback_system = None  # Fallback if feedback system is not available


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
        # print("🚀 NewsProcessingPipeline initialized with enhanced SmartNewsFetcher") # Minimize logs

    def get_all_users(self) -> List[Any]:
        """Get all registered users from the system."""
        users = []
        for user_id in USER_PROFILES.keys():
            user = get_user_profile(user_id)
            if user:
                users.append(user)
        # print(f"👥 Loaded {len(users)} users from system") # Minimize logs
        return users

    def _generate_ynk_summary(self, article: Dict) -> str:
        """Generates a YNK (Why Not Care) summary for an article using summarizer.py."""
        if not self.summarize_news_func:
            return "Summary generation module (summarizer.py) not available."

        try:
            # Use article content, description, or title
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

    def _get_article_topic_key(self, article: Dict) -> Tuple[str, str]:
        """Generate a key representing the main topic of an article to avoid duplicates."""
        category = article.get("category", "general")
        subcategory = (
            article.get("sports_subcategory")
            or article.get("economy_subcategory")
            or article.get("tech_subcategory")
            or "general"
        )
        return (category, subcategory)

    def _select_top_articles_for_user(
        self, news_bundle: Dict[str, List[Dict]], user_profile: Dict
    ) -> List[Dict]:
        """
        Selects the TOP-7 articles for a specific user from the news_bundle.
        Prioritizes user's specific interests and guarantees representation from them if possible,
        with quality thresholds and duplicate topic avoidance.
        """
        # --- Configuration ---
        MIN_IMPORTANCE_FOR_GUARANTEE = 45  # Minimum importance for a guaranteed article
        MIN_RELEVANCE_FOR_GUARANTEE = 0.40  # Minimum relevance for a guaranteed article
        # --- End Configuration ---

        selected_articles = []
        seen_titles: Set[str] = set()  # For deduplication by title
        selected_article_topics: Set[
            Tuple[str, str]
        ] = set()  # For deduplication by topic
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
                        article.get("tech_subcategory"),
                    ]
                    if subcategory in article_subcats:
                        # Apply quality threshold for guaranteed articles
                        if (
                            article.get("importance_score", 0)
                            >= MIN_IMPORTANCE_FOR_GUARANTEE
                            and article.get("relevance_score", 0)
                            >= MIN_RELEVANCE_FOR_GUARANTEE
                        ):
                            matching_articles.append(article)

            # Sort by relevance and pick the best unique one that doesn't duplicate topic
            matching_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )
            article_added_for_this_subcat = False
            for article in matching_articles:
                title_key = article.get("title", "").lower()
                topic_key = self._get_article_topic_key(article)
                if (
                    title_key not in seen_titles
                    and topic_key not in selected_article_topics
                    and len(selected_articles) < 7
                    and not article_added_for_this_subcat
                ):  # Only one article per subcategory guarantee
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    selected_article_topics.add(topic_key)
                    # print(f"📌 Guaranteed article for specific subcategory '{subcategory}': {article.get('title', 'No Title')[:50]}...") # Minimize logs
                    article_added_for_this_subcat = True
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
            # Only add if we haven't filled the quota and this category wasn't strongly covered by subcats
            if len(selected_articles) >= 7:
                break

            category_articles = news_bundle.get(category, [])
            # Apply quality threshold for guaranteed articles
            qualified_category_articles = [
                a
                for a in category_articles
                if (
                    a.get("importance_score", 0) >= MIN_IMPORTANCE_FOR_GUARANTEE
                    and a.get("relevance_score", 0) >= MIN_RELEVANCE_FOR_GUARANTEE
                )
            ]
            qualified_category_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )

            article_added_for_this_cat = False
            for article in qualified_category_articles:
                title_key = article.get("title", "").lower()
                topic_key = self._get_article_topic_key(article)
                if (
                    title_key not in seen_titles
                    and topic_key not in selected_article_topics
                    and len(selected_articles) < 7
                    and not article_added_for_this_cat
                ):  # Only one article per main category guarantee
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    selected_article_topics.add(topic_key)
                    # print(f"📌 Guaranteed article for main category '{category}': {article.get('title', 'No Title')[:50]}...") # Minimize logs
                    article_added_for_this_cat = True
                    break  # Take only the first match for this main category

        # c. Fill remaining slots with the best articles overall, avoiding topic duplicates
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
                topic_key = self._get_article_topic_key(article)
                if (
                    title_key not in seen_titles
                    and topic_key not in selected_article_topics
                ):
                    selected_articles.append(article)
                    seen_titles.add(title_key)
                    selected_article_topics.add(topic_key)
                    # print(f"🔝 Added to TOP-7 (filler): {article.get('title', 'No Title')[:50]}... (Score: {article.get('relevance_score', 0):.2f})") # Minimize logs

        # print(f"✅ Final TOP-7 selection complete. Total articles: {len(selected_articles)}") # Minimize logs
        return selected_articles

    def process_daily_news(self, user_preferences: Dict) -> Dict[str, List[Dict]]:
        """
        Process daily news batch for a user.
        NOTE: This is a SYNCHRONOUS method, not async!

        Args:
            user_preferences: User profile with locale, interests, language preferences

        Returns:
            Dictionary containing the 'top_7' articles
        """
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

        # Group articles by category for ordered display
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


if __name__ == "__main__":
    # Initialize pipeline
    pipeline = NewsProcessingPipeline(max_workers=3)

    # Test with sample user preferences (like your Maxonchik profile)
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

    # Process daily news (SYNCHRONOUS CALL!) - now returns TOP-7
    result = pipeline.process_daily_news(sample_preferences)
    top_7_articles = result.get("top_7", [])

    # The final output is already inside process_daily_news, so we can just finish here
    # print(f"\n🏁 Pipeline execution completed.") # Minimize logs
