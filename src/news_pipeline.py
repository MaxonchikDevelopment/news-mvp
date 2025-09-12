# src/news_pipeline.py
"""Complete news processing pipeline with real user integration and feedback."""

import asyncio
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List


# --- Path setup ---
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
    from feedback_system import feedback_system

    print("✅ Imported feedback_system successfully")
except ImportError as e:
    print(f"❌ Failed to import feedback_system: {e}")
    feedback_system = None  # Fallback если система фидбека не доступна


class NewsProcessingPipeline:
    def __init__(self, max_workers: int = 5):
        """
        Initialize the complete news processing pipeline.

        Args:
            max_workers: Maximum number of concurrent tasks
        """
        self.max_workers = max_workers
        self.fetcher = SmartNewsFetcher()  # Используем улучшенный фетчер
        self.cache = get_cache_manager()
        self.feedback_system = feedback_system
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

    def process_daily_news(self, user_preferences: Dict) -> Dict[str, List[Dict]]:
        """
        Process daily news batch for all users.
        NOTE: This is a SYNCHRONOUS method, not async!

        Args:
            user_preferences: User profile with locale, interests, language preferences

        Returns:
            Dictionary mapping user_id to their personalized feed
        """
        print(f"\n{'='*60}")
        print(f"📅 DAILY NEWS PROCESSING - {datetime.now().strftime('%Y-%m-%d')}")
        print(f"📰 News items: {len(user_preferences.get('interests', []))}")
        print(f"👥 Users: {len(self.get_all_users())}")
        print(f"{'='*60}")

        start_time = time.time()

        # Get all users
        users = self.get_all_users()

        # Process news using enhanced fetcher
        print("🔄 Fetching and processing news with enhanced SmartNewsFetcher...")
        news_bundle = self.fetcher.fetch_daily_news_bundle(user_preferences)

        end_time = time.time()
        processing_time = end_time - start_time

        # Update statistics
        self.processed_news_count += len(news_bundle)
        self.total_processing_time += processing_time

        # Print summary
        self._print_processing_summary(news_bundle, user_preferences, processing_time)

        return news_bundle

    def _print_processing_summary(
        self,
        news_bundle: Dict[str, List[Dict]],
        user_preferences: Dict,
        processing_time: float,
    ):
        """Print detailed processing summary."""
        print(f"\n{'='*60}")
        print(f"📊 PROCESSING SUMMARY")
        print(f"{'='*60}")
        print(f"⏱️  Total time: {processing_time:.2f} seconds")
        print(
            f"⚡ Performance: {sum(len(articles) for articles in news_bundle.values()) / max(processing_time, 0.001):.1f} articles/second"
        )
        print(f"💾 Cache items: {len(self.cache._cache)}")

        print(f"\n📋 NEWS BUNDLE:")
        total_articles = 0
        for category, articles in news_bundle.items():
            print(f"  📁 {category.upper()}: {len(articles)} articles")
            total_articles += len(articles)
            if articles:
                top_article = max(articles, key=lambda x: x.get("relevance_score", 0))
                print(
                    f"     🏆 Top priority: {top_article.get('relevance_score', 0):.2f}/1.00 [{top_article.get('category')}]"
                )

        print(f"\n📈 CUMULATIVE STATS:")
        print(f"   Total articles processed: {self.processed_news_count}")
        print(f"   Total processing time: {self.total_processing_time:.2f} seconds")
        if self.processed_news_count > 0:
            print(
                f"   Average time per article: {self.total_processing_time/self.processed_news_count:.3f} seconds"
            )


# Test execution for MVP
if __name__ == "__main__":
    # Initialize pipeline
    pipeline = NewsProcessingPipeline(max_workers=3)

    # Test with sample user preferences (like your Maxonchik profile)
    sample_preferences = {
        "user_id": "Maxonchik",
        "locale": "DE",
        "language": "en",
        "city": "Frankfurt",
        "interests": [
            "economy_finance",
            "technology_ai_science",
            {"sports": ["basketball_nba", "football_epl", "formula1"]},
        ],
    }

    print("🚀 Testing NewsProcessingPipeline with sample preferences...")

    # Process daily news (SYNCHRONOUS CALL!)
    news_bundle = pipeline.process_daily_news(sample_preferences)

    # Display detailed results
    print(f"\n{'='*80}")
    print(f"📱 DETAILED NEWS BUNDLE RESULTS")
    print(f"{'='*80}")

    total_articles = sum(len(articles) for articles in news_bundle.values())
    print(f"📊 Total articles: {total_articles}")

    for category, articles in news_bundle.items():
        print(f"\n📁 {category.upper()}: {len(articles)} articles")
        # Sort by relevance score for better display
        sorted_articles = sorted(
            articles, key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        for i, article in enumerate(sorted_articles[:5]):  # Show top 5 per category
            print(f"\n  📰 {i+1}. {article['title'][:60]}...")
            print(
                f"     Source: {article['source']} | Score: {article.get('relevance_score', 0):.2f}"
            )
            print(
                f"     Language: {article.get('language')} → {sample_preferences['language']}"
            )
            if article.get("ai_classified"):
                print(
                    f"     AI Confidence: {article.get('confidence', 0):.2f} | Importance: {article.get('importance_score', 0)}/100"
                )
                if "contextual_factors" in article:
                    ctx = article["contextual_factors"]
                    print(
                        f"     Context: Global {ctx.get('global_impact', 'N/A')}, Time {ctx.get('time_sensitivity', 'N/A')}"
                    )

    print(f"\n{'='*80}")
