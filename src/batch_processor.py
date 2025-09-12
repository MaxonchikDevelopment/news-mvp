"""Batch processing optimization with persistent caching for improved performance."""

import asyncio
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple


# --- Path setup ---
def setup_paths():
    """Setup paths for correct imports."""
    current_dir = os.path.dirname(__file__)
    root_dir = os.path.dirname(current_dir)

    # Add root directory and src to path
    paths_to_add = [root_dir, current_dir]
    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)


setup_paths()

# Import modules
from cache_manager import get_cache_manager
from enhanced_prioritizer import adjust_priority_with_feedback


class BatchNewsProcessor:
    def __init__(self, max_workers: int = 5, feedback_system=None):
        """
        Initialize the batch news processor.

        Args:
            max_workers: Maximum number of concurrent tasks
            feedback_system: Feedback system for preference-based prioritization
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cache = get_cache_manager()  # Use singleton cache
        self.feedback_system = feedback_system  # Feedback system for personalization
        print(f"BatchNewsProcessor initialized with {max_workers} workers")

    async def process_news_batch_for_users(
        self, news_list: List[str], users: List[Any]
    ) -> Dict[str, List[Dict]]:
        """
        Process news batch and generate personalized feeds for all users.

        Args:
            news_list: List of news texts to process
            users: List of user profiles

        Returns:
            Dictionary mapping user_id to their personalized feed
        """
        print(f"Processing {len(news_list)} news items for {len(users)} users...")

        # Step 1: Batch classification and summarization with caching
        classifications, summaries = await self.process_news_batch(news_list)

        # Step 2: Generate personalized feeds for each user
        user_feeds = await self._generate_personalized_feeds(
            classifications, summaries, users, news_list
        )

        return user_feeds

    async def process_news_batch(
        self, news_list: List[str]
    ) -> Tuple[List[Dict], List[str]]:
        """
        Process a batch of news items: classify and summarize with caching.

        Returns:
            Tuple of (classifications, summaries)
        """
        print(f"Starting processing of {len(news_list)} news items...")

        # Step 1: Batch classification with caching
        classifications = await self._batch_classify_with_cache(news_list)

        # Step 2: Batch summarization with caching
        summaries = await self._batch_summarize_with_cache(news_list, classifications)

        return classifications, summaries

    async def _batch_classify_with_cache(self, news_list: List[str]) -> List[Dict]:
        """Batch classification with caching support."""
        print(f"Classifying {len(news_list)} news items (with cache)...")

        from classifier import classify_news

        loop = asyncio.get_event_loop()
        tasks = []
        cache_results = []

        # Check cache first
        for i, news in enumerate(news_list):
            cached_result = self.cache.get(news, "classification")
            if cached_result:
                cache_results.append((i, cached_result))
            else:
                # Prepare for async processing
                task = loop.run_in_executor(
                    self.executor, self._classify_with_cache, news
                )
                tasks.append((i, task))
                print(f"✓ Prepared news item {i+1} for classification")

        # Process uncached items
        processed_results = []
        if tasks:
            try:
                task_results = await asyncio.gather(*[task for _, task in tasks])
                processed_results = [
                    (tasks[i][0], result) for i, result in enumerate(task_results)
                ]
                print("New classifications completed!")
            except Exception as e:
                print(f"Classification error: {e}")
                # Fallback to sequential processing for uncached items
                uncached_indices = [i for i, _ in tasks]
                uncached_news = [news_list[i] for i in uncached_indices]
                sequential_results = await self._sequential_classify(uncached_news)
                processed_results = list(zip(uncached_indices, sequential_results))

        # Combine cached and processed results
        all_results = cache_results + processed_results
        all_results.sort(key=lambda x: x[0])  # Sort by index

        return [result for _, result in all_results]

    def _classify_with_cache(self, text: str) -> Dict:
        """Classify single news item with cache support."""
        # Check cache
        cached = self.cache.get(text, "classification")
        if cached:
            return cached

        # Process and cache
        from classifier import classify_news

        result = classify_news(text)
        self.cache.set(text, "classification", result)
        return result

    async def _batch_summarize_with_cache(
        self, news_list: List[str], classifications: List[Dict]
    ) -> List[str]:
        """Batch summarization with caching support."""
        print(f"Summarizing {len(news_list)} news items (with cache)...")

        from summarizer import summarize_news

        loop = asyncio.get_event_loop()
        tasks = []
        cache_results = []

        # Check cache and prepare tasks
        for i, (news, classification) in enumerate(zip(news_list, classifications)):
            category = classification.get("category", "economy_finance")
            cache_key = f"{news[:100]}_{category}"  # Simple cache key

            cached_result = self.cache.get(cache_key, "summarization")
            if cached_result:
                cache_results.append((i, cached_result))
            else:
                task = loop.run_in_executor(
                    self.executor, self._summarize_with_cache, news, category, cache_key
                )
                tasks.append((i, task))
                print(f"✓ Prepared news item {i+1} for summarization")

        # Process uncached items
        processed_results = []
        if tasks:
            try:
                task_results = await asyncio.gather(*[task for _, task in tasks])
                processed_results = [
                    (tasks[i][0], result) for i, result in enumerate(task_results)
                ]
                print("New summaries completed!")
            except Exception as e:
                print(f"Summarization error: {e}")
                # Fallback to sequential processing
                uncached_data = [
                    (i, news_list[i], classifications[i]) for i, _ in tasks
                ]
                sequential_results = []
                for i, news, classification in uncached_data:
                    category = classification.get("category", "economy_finance")
                    cache_key = f"{news[:100]}_{category}"
                    try:
                        result = self._summarize_with_cache(news, category, cache_key)
                        sequential_results.append((i, result))
                    except Exception as e:
                        print(f"Error summarizing news item {i}: {e}")
                        sequential_results.append((i, "Summary generation failed"))
                processed_results = sequential_results

        # Combine results
        all_results = cache_results + processed_results
        all_results.sort(key=lambda x: x[0])

        return [result for _, result in all_results]

    def _summarize_with_cache(self, text: str, category: str, cache_key: str) -> str:
        """Summarize single news item with cache support."""
        # Check cache
        cached = self.cache.get(cache_key, "summarization")
        if cached:
            return cached

        # Process and cache
        from summarizer import summarize_news

        result = summarize_news(text, category)
        self.cache.set(cache_key, "summarization", result)
        return result

    async def _generate_personalized_feeds(
        self,
        classifications: List[Dict],
        summaries: List[str],
        users: List[Any],
        original_news: List[str],
    ) -> Dict[str, List[Dict]]:
        """Generate personalized feeds for all users."""
        print(f"Generating personalized feeds for {len(users)} users...")

        user_feeds = {}

        # Process each user
        for user in users:
            user_id = getattr(user, "user_id", "unknown_user")
            print(f"Generating feed for user: {user_id}")

            user_feed = []
            for i, (classification, summary, original_text) in enumerate(
                zip(classifications, summaries, original_news)
            ):
                # Calculate personalized priority with feedback enhancement
                try:
                    priority = adjust_priority_with_feedback(
                        classification,
                        user,
                        original_text,
                        feedback_system=self.feedback_system,
                    )

                    # Only include relevant news (priority > 30)
                    if priority > 30:
                        feed_item = {
                            "news_id": i,
                            "category": classification.get("category", "unknown"),
                            "summary": summary,
                            "priority": priority,
                            "confidence": classification.get("confidence", 0),
                            "original_text": original_text[:100]
                            + "...",  # Short preview
                        }
                        user_feed.append(feed_item)
                except Exception as e:
                    print(
                        f"Error calculating priority for user {user_id}, news {i}: {e}"
                    )

            # Sort by priority (highest first)
            user_feed.sort(key=lambda x: x["priority"], reverse=True)
            user_feeds[user_id] = user_feed

            print(
                f"✓ Generated feed for {user_id} with {len(user_feed)} relevant items"
            )

        return user_feeds

    async def _sequential_classify(self, news_list: List[str]) -> List[Dict]:
        """Fallback sequential classification."""
        print("Falling back to sequential classification...")
        results = []
        for i, news in enumerate(news_list):
            try:
                result = self._classify_with_cache(news)
                results.append(result)
                print(f"✓ Classified news item {i+1} sequentially")
            except Exception as e:
                print(f"Error classifying news item {i+1}: {e}")
                results.append(
                    {
                        "category": "unknown",
                        "confidence": 0.0,
                        "priority_llm": 0,
                        "reasons": "Classification failed",
                    }
                )
        return results


# Test execution
if __name__ == "__main__":
    processor = BatchNewsProcessor()

    # Test news
    test_news = [
        """In a thrilling NBA Finals Game 7, the Miami Heat edged out the Los Angeles Lakers 112-110
        to clinch the championship. Jimmy Butler scored 35 points, including the game-winning free throws
        with just seconds left. LeBron James had a triple-double for the Lakers but missed a potential
        game-tying shot at the buzzer.""",
        """ECB announces surprise interest rate cut to stimulate economic growth amid rising inflation concerns.
        The move affects all Eurozone countries and impacts mortgage rates across the region. Financial markets
        reacted positively to the unexpected decision.""",
    ]

    # Test user profile
    class MockUser:
        def __init__(self, user_id, interests, locale="DE", city="Frankfurt"):
            self.user_id = user_id
            self.interests = interests
            self.locale = locale
            self.city = city
            self.language = "en"

    # Create test users
    test_users = [
        MockUser("sports_fan", ["sports", "technology_ai_science"]),
        MockUser("finance_expert", ["economy_finance", "politics_geopolitics"]),
    ]

    # Async test function
    async def test_batch():
        start_time = time.time()
        user_feeds = await processor.process_news_batch_for_users(test_news, test_users)
        end_time = time.time()

        print(f"\n{'='*70}")
        print(f"Total processing time: {end_time - start_time:.2f} seconds")
        print(f"Processed {len(test_news)} news items for {len(test_users)} users")
        print(f"CACHE STATS: {len(processor.cache._cache)} items in cache")
        print(f"{'='*70}")

        # Display results
        for user_id, feed in user_feeds.items():
            print(f"\n📱 Personalized Feed for {user_id}:")
            print("-" * 50)

            if not feed:
                print("  No relevant news for this user")
            else:
                for i, item in enumerate(feed):
                    print(
                        f"  {i+1}. Priority {item['priority']}/100 [{item['category']}]"
                    )
                    summary_lines = item["summary"].split("\n")
                    if len(summary_lines) > 0:
                        print(f"     {summary_lines[0]}")
                        if len(summary_lines) > 1:
                            print(f"     {summary_lines[1][:80]}...")

    asyncio.run(test_batch())
