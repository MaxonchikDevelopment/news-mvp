# src/news_fetcher.py
"""Smart News Fetcher - Custom implementation for global personalized news delivery.
Fetches from multiple sources, handles multilingual content, and prepares for MVP.
"""

import hashlib
import json
import os
import re  # Added for potential content cleaning
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Union

import requests
from dotenv import load_dotenv

# --- Path setup for internal imports ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import classifier module function directly
try:
    from src.classifier import classify_news

    CLASSIFIER_IMPORTED = True
except ImportError as e:
    print(f"⚠️ Classifier function not available: {e}")
    CLASSIFIER_IMPORTED = False
    classify_news = None

# Load environment variables
load_dotenv()


class SmartNewsFetcher:
    """Intelligent news fetching with global coverage and smart filtering."""

    def __init__(self):
        """Initialize the news fetcher with configuration."""
        self.api_keys = {
            "newsapi": os.getenv("NEWSAPI_KEY"),
            "guardian": os.getenv("GUARDIAN_KEY"),
            # Reddit keys removed as per request
        }

        # Configure quality filters - Relaxed criteria
        self.quality_filters = {
            "min_length": 50,  # Slightly increased minimum length for better content
            # 'max_length': 100000, # Removed max length limit
            "required_fields": ["title"],  # Only title is strictly required now
            # Removed some overly restrictive banned keywords
            "banned_keywords": ["advertisement", "sponsored", "deal of the day"],
        }

        # RSS feed sources - Expanded and cleaned list for better global coverage
        # Focused on increasing sports representation and overall volume
        self.rss_feeds = [
            # Global English News
            "http://feeds.bbci.co.uk/news/rss.xml",
            "https://rss.cnn.com/rss/edition.rss",
            "https://feeds.reuters.com/reuters/topNews",
            "https://www.aljazeera.com/xml/rss/all.xml",
            # Technology & Science
            "https://feeds.feedburner.com/oreilly/radar",
            "https://techcrunch.com/feed/",
            "https://www.wired.com/feed/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://www.sciencedaily.com/rss/all.xml",
            # Finance & Economics
            "https://www.ft.com/rss/home",
            "https://www.economist.com/the-world-this-week/rss.xml",
            "https://www.economist.com/finance-and-economics/rss.xml",
            # Culture & Entertainment
            "https://www.reddit.com/r/entertainment/.rss",  # Using Reddit for this category as content source
            # --- Sports RSS Feeds ---
            # General Sports
            "https://www.espn.com/espn/rss/news",
            # Football/Soccer
            "http://www.espnfc.com/rss",  # ESPN FC
            "https://www.skysports.com/rss/12040",  # Sky Sports Football
            # NBA
            "https://www.nba.com/rss/news",
            # Formula 1
            "https://www.formula1.com/en/latest/all.xml",
            # Bundesliga
            "https://www.bundesliga.com/en/news/rss.xml",
            # NFL
            "https://www.nfl.com/feeds/rss/news",
            # Tennis
            "https://www.atptour.com/en/media/rss/news.xml",  # ATP
            # Euroleague Basketball
            "https://www.euroleague.net/rss/news",  # Check if this works
            # Olympics (if seasonal feeds are available, they can be added)
            # German News (for locale relevance)
            "https://www.spiegel.de/international/index.rss",
            "https://www.dw.com/search/en/rss?searchNavigationId=9038",
            # Additional General/World News
            "https://rss.dw.com/xml/rss-en-all",
            "https://www.france24.com/en/rss",
            "https://www.bbc.com/news/rss.xml",  # BBC World
        ]

        # Map user interest categories to Guardian section IDs
        self.guardian_category_map = {
            "politics_geopolitics": "politics",
            "economy_finance": "business",
            "technology_ai_science": "technology",
            "sports": "sport",
            "culture_media_entertainment": "culture",
            "healthcare_pharma": "society/health",
            "energy_climate_environment": "environment",
            "real_estate_housing": "money/property",
            "career_education_labour": "education",
            "transport_auto_aviation": "business/aviation",
        }

        # Print initialization status
        self._print_initialization_status()

    def _print_initialization_status(self):
        """Print the initialization status of different sources."""
        print("🌍 SmartNewsFetcher initialized with global coverage")
        print("📊 Source Configuration:")
        print("  PREMIUM:")
        status_newsapi = "✅ ENABLED" if self.api_keys["newsapi"] else "❌ DISABLED"
        status_guardian = "✅ ENABLED" if self.api_keys["guardian"] else "❌ DISABLED"
        print(f"    newsapi: {status_newsapi}")
        print(f"    guardian: {status_guardian}")
        print("  FREE:")
        try:
            import feedparser

            status_rss = "✅ ENABLED"
        except ImportError:
            status_rss = "❌ DISABLED (feedparser not installed)"
        print(f"    rss: {status_rss}")
        # Reddit explicitly removed
        print("    reddit: ❌ DISABLED (Removed by user request)")

    def _fetch_guardian_articles(
        self, categories_to_fetch: List[str], user_locale: str
    ) -> List[Dict]:
        """Fetch articles from The Guardian API."""
        if not self.api_keys["guardian"]:
            return []

        articles = []
        guardian_url = "https://content.guardianapis.com/search"  # Fixed URL

        # Date for yesterday to get fresh news
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Increase the number of categories fetched from Guardian
        categories_to_fetch_limited = categories_to_fetch[:5]  # Increased from 3

        for user_category in categories_to_fetch_limited:
            # Map user category to Guardian section ID
            guardian_section = self.guardian_category_map.get(user_category)
            if not guardian_section:
                print(
                    f"  ⚠️ No Guardian section mapping for user category '{user_category}', skipping."
                )
                continue

            # Increase page size to limit articles
            params = {
                "api-key": self.api_keys["guardian"],
                "section": guardian_section,
                "from-date": yesterday,
                "to-date": yesterday,
                "page-size": 5,  # Increased from 10, make 15 to add more
                "show-fields": "headline,trailText,body",
                "order-by": "relevance",
            }

            try:
                response = requests.get(
                    guardian_url, params=params, timeout=15
                )  # Increased timeout
                response.raise_for_status()
                data = response.json()

                results = data.get("response", {}).get("results", [])

                for item in results:
                    article = {
                        "source": "The Guardian",
                        "title": item.get("webTitle", ""),
                        "description": item.get("fields", {}).get("trailText", ""),
                        "content": item.get("fields", {}).get("body", ""),
                        "url": item.get("webUrl", ""),
                        "published_at": item.get("webPublicationDate"),
                        "category": user_category,  # Keep user's category name for consistency
                    }
                    # Basic check to ensure we have at least a title
                    if article["title"]:
                        articles.append(article)

            except requests.exceptions.RequestException as e:
                print(
                    f"⚠️ Guardian fetch error for category {user_category} ({guardian_section}): {e}"
                )
            except Exception as e:
                print(
                    f"⚠️ Unexpected Guardian error for category {user_category} ({guardian_section}): {e}"
                )

        return articles

    def _fetch_rss_articles(self) -> List[Dict]:
        """Fetch articles from RSS feeds."""
        try:
            import feedparser
        except ImportError:
            print("⚠️ feedparser not installed. Skipping RSS feeds.")
            return []

        articles = []
        # Increase total RSS feeds processed to control volume
        feeds_to_process = self.rss_feeds[:5]  # Increased from 25, 35 for more volume

        for url in feeds_to_process:
            try:
                clean_url = url.strip()
                if not clean_url:  # Skip empty strings
                    continue
                feed = feedparser.parse(clean_url)
                # Increase articles per feed
                entries_to_process = feed.entries[:10]  # Increased from 7

                for entry in entries_to_process:
                    article = {
                        "source": getattr(feed.feed, "title", clean_url),
                        "title": getattr(entry, "title", ""),
                        "description": getattr(entry, "summary", ""),
                        "content": getattr(entry, "content", [{}])[0].get("value", "")
                        if hasattr(entry, "content")
                        else "",
                        "url": getattr(entry, "link", ""),
                        "published_at": getattr(entry, "published", None),
                    }
                    # Prioritize content, fallback to description
                    if not article["content"] and article["description"]:
                        article["content"] = article["description"]

                    # Basic check to ensure we have at least a title
                    if article["title"]:
                        articles.append(article)
            except Exception as e:
                # Minimal error logging for RSS to avoid spam
                # print(f"⚠️ RSS fetch error for {url[:50]}...: {e}")
                pass

        return articles

    # Reddit method removed entirely

    def _is_high_quality_article(self, article: Dict) -> bool:
        """Check if an article meets relaxed quality criteria."""
        title = article.get("title", "")

        # Must have a title
        if not title:
            return False

        content = article.get("content", "") or article.get("description", "")

        # Check minimum content length
        if len(content) < self.quality_filters["min_length"]:
            return False

        # Check for banned keywords
        full_text = f"{title} {content}".lower()
        if any(
            keyword in full_text for keyword in self.quality_filters["banned_keywords"]
        ):
            return False

        return True

    def _deduplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on title hash."""
        seen_hashes = set()
        unique_articles = []
        for article in articles:
            title_hash = hashlib.md5(article["title"].encode("utf-8")).hexdigest()
            if title_hash not in seen_hashes:
                seen_hashes.add(title_hash)
                unique_articles.append(article)
        return unique_articles

    def _classify_articles(self, articles: List[Dict], user_locale: str) -> List[Dict]:
        """Classify articles using AI or fallback keyword method."""
        # Используем только импортированную функцию classify_news
        if not classify_news:
            print("  ⚠️ AI classifier not available, using keyword classification")
            return self._classify_articles_keyword_fallback(articles)

        print("  🔍 FORCING AI classification call...")
        print("  🧠 Classifying articles with AI... ENTERING METHOD")

        classified_articles = []
        for i, article in enumerate(articles):
            try:
                # Combine title and description for classification
                text_to_classify = (
                    f"{article.get('title', '')} {article.get('description', '')}"
                )

                # Call the imported classify_news function
                classification_result = classify_news(
                    text_to_classify, user_locale=user_locale
                )

                article.update(classification_result)
                article["ai_classified"] = True
                classified_articles.append(article)

            except Exception as e:
                print(
                    f"    ⚠️ AI classification error for article {i+1} ({article.get('title', 'No Title')[:30]}...): {type(e).__name__}: {e}"
                )
                # Fallback to keyword classification on error
                keyword_classified = self._classify_single_article_keyword_fallback(
                    article
                )
                article.update(keyword_classified)
                article["ai_classified"] = False
                classified_articles.append(article)

        print(f"   ✅ AI classified {len(classified_articles)}/{len(articles)} articles")
        return classified_articles

    def _classify_single_article_keyword_fallback(self, article: Dict) -> Dict:
        """Classify a single article using keywords."""
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()
        category_keywords = {
            "politics_geopolitics": [
                "politic",
                "government",
                "election",
                "war",
                "sanction",
                "diplomat",
                "minister",
                "president",
                "prime minister",
                "parliament",
                "congress",
            ],
            "economy_finance": [
                "economy",
                "finance",
                "market",
                "stock",
                "inflation",
                "recession",
                "bank",
                "trade",
                "gdp",
                "fiscal",
                "monetary",
                "currency",
                "bitcoin",
                "crypto",
            ],
            "technology_ai_science": [
                "technology",
                "tech",
                "ai",
                "artificial intelligence",
                "science",
                "research",
                "chip",
                "software",
                "innovation",
                "algorithm",
                "silicon valley",
                "startup",
                "cyber",
            ],
            "sports": [
                "sport",
                "football",
                "soccer",
                "basketball",
                "tennis",
                "match",
                "league",
                "championship",
                "tournament",
                "player",
                "champion",
                "cup",
                "world cup",
            ],
            "culture_media_entertainment": [
                "culture",
                "movie",
                "film",
                "music",
                "celebrity",
                "art",
                "book",
                "entertainment",
                "show",
                "actor",
                "actress",
                "tv",
                "hollywood",
            ],
            "healthcare_pharma": [
                "health",
                "medical",
                "disease",
                "vaccine",
                "hospital",
                "doctor",
                "pharma",
                "treatment",
                "covid",
                "pandemic",
                "drug",
                "therapy",
            ],
            "energy_climate_environment": [
                "energy",
                "climate",
                "environment",
                "oil",
                "gas",
                "renewable",
                "solar",
                "wind",
                "pollution",
                "carbon",
                "emission",
                "greenhouse",
            ],
            "real_estate_housing": [
                "real estate",
                "housing",
                "property",
                "mortgage",
                "home",
                "apartment",
                "rent",
                "buy house",
                "housing market",
            ],
            "career_education_labour": [
                "job",
                "career",
                "education",
                "university",
                "school",
                "work",
                "employment",
                "graduate",
                "salary",
                "unemployment",
                "degree",
            ],
            "transport_auto_aviation": [
                "car",
                "auto",
                "transport",
                "aviation",
                "flight",
                "airline",
                "train",
                "bus",
                "traffic",
                "tesla",
                "electric vehicle",
            ],
        }

        scores = {cat: 0 for cat in category_keywords}
        for category, keywords in category_keywords.items():
            scores[category] = sum(1 for keyword in keywords if keyword in text)

        best_category = max(scores, key=scores.get)
        # Avoid division by zero
        total_score = sum(scores.values())
        if total_score == 0:
            confidence = 0.0
        else:
            confidence = scores[best_category] / total_score

        default_contextual_factors = {
            "time_sensitivity": 50,
            "global_impact": 50,
            "personal_relevance": 50,
            "historical_significance": 50,
            "emotional_intensity": 50,
        }

        return {
            "category": best_category,
            "confidence": round(confidence, 2),
            "reasons": "Keyword-based classification",
            "importance_score": int(confidence * 50),  # Map confidence to 0-100 scale
            "contextual_factors": default_contextual_factors,
        }

    def _classify_articles_keyword_fallback(self, articles: List[Dict]) -> List[Dict]:
        """Fallback classification using keywords for all articles."""
        classified_articles = []
        for article in articles:
            classification = self._classify_single_article_keyword_fallback(article)
            article.update(classification)
            article["ai_classified"] = False
            classified_articles.append(article)
        return classified_articles

    def _score_article_relevance(
        self, article: Dict, user_interests: List[Any], user_locale: str
    ) -> float:
        """
        Calculate a personalized relevance score (0.0 to 1.0) for an article.
        Based on importance_score (0-100) and user preferences.
        Improved algorithm with better calibration and enhanced sports boost.
        """
        importance_score = article.get(
            "importance_score", 50
        )  # Default to 50 if missing

        # --- Relevance Score Calculation (0-100) ---
        base_score = importance_score

        interest_bonus = 0
        # Bonus for matching user interests (slightly increased)
        article_category = article.get("category", "")
        article_sports_subcat = article.get("sports_subcategory", "")
        article_econ_subcat = article.get("economy_subcategory", "")
        article_tech_subcat = article.get("tech_subcategory", "")

        # Check main categories and subcategories
        for interest in user_interests:
            if isinstance(interest, str) and interest == article_category:
                interest_bonus = max(interest_bonus, 13)  # Increased from 12
                break
            elif isinstance(interest, dict):
                main_cat = list(interest.keys())[0]
                subcats = interest[main_cat]
                if isinstance(subcats, list):
                    # Check if article's subcategory matches user's specific interests
                    if (
                        (main_cat == article_category)
                        and (
                            not article_sports_subcat
                            or article_sports_subcat in subcats
                        )
                        and (not article_econ_subcat or article_econ_subcat in subcats)
                        and (not article_tech_subcat or article_tech_subcat in subcats)
                    ):
                        interest_bonus = max(
                            interest_bonus, 15
                        )  # Bonus for matching specific subcategory
                        break

        locale_bonus = 0
        # Bonus for locale relevance (increased potential max bonus)
        article_content = article.get("content", "").lower()
        article_title = article.get("title", "").lower()
        user_locale_lower = user_locale.lower()

        if user_locale_lower in article_title or user_locale_lower in article_content:
            context_words = [
                "in " + user_locale_lower,
                "from " + user_locale_lower,
                user_locale_lower + " government",
                user_locale_lower + " president",
                user_locale_lower + " economy",
                user_locale_lower + " market",
            ]
            if any(
                word in article_title or word in article_content
                for word in context_words
            ):
                locale_bonus = 10  # Increased from 8
            else:
                locale_bonus = 5  # Increased from 3

        category_boost = 0
        # Boosts for specific high-value categories
        if article_category == "technology_ai_science" and importance_score >= 80:
            category_boost = 4
        elif article_category == "technology_ai_science" and importance_score >= 70:
            category_boost = 2
        elif article_category == "economy_finance" and importance_score >= 80:
            category_boost = 2

        # --- NEW: Enhanced Sports Boost ---
        sport_high_impact_boost = 0
        # Give an extra boost to high-importance sports news
        if article_category == "sports" and importance_score >= 70:
            sport_high_impact_boost = 3  # New boost for important sports events
        # --- END NEW ---

        low_imp_penalty = 0
        # Penalty for low importance in generally interesting categories
        if (
            article_category in ["sports", "technology_ai_science", "economy_finance"]
            and importance_score < 60
        ):
            low_imp_penalty = -15

        # Additional penalty for very low importance articles that still match interests
        if importance_score < 40 and interest_bonus > 0:
            low_imp_penalty -= 5

        # Calculate raw score
        raw_score = (
            base_score
            + interest_bonus
            + locale_bonus
            + category_boost
            + low_imp_penalty
            + sport_high_impact_boost
        )

        # Cap the score with a softer limit
        if raw_score > 95:
            capped_score = 95 + (raw_score - 95) * 0.5
        else:
            capped_score = raw_score

        final_score_0_100 = max(0, min(100, capped_score))

        # Normalize to 0.0 - 1.0 for sorting
        final_score_0_1 = final_score_0_100 / 100.0

        article["relevance_score"] = final_score_0_1
        # print(f"    🎯 Relevance score calculated: {final_score_0_100:.1f}/100 ({final_score_0_1:.2f})") # Minimized log
        return final_score_0_1

    def _prepare_news_bundle(
        self, articles: List[Dict], user_interests: List[Any], user_locale: str
    ) -> Dict[str, List[Dict]]:
        """Prepare the final news bundle grouped by category."""
        print("   ✅ Relevance scoring: ... articles", end="")  # Dynamic log
        scored_articles = []
        for article in articles:
            # Note: Errors in scoring will silently drop the article from the scored list
            # Consider if you want a default score for articles that fail scoring
            try:
                score = self._score_article_relevance(
                    article, user_interests, user_locale
                )
                scored_articles.append(article)
            except Exception:
                pass  # Article dropped if scoring fails
        print(f"\r   ✅ Relevance scoring: {len(scored_articles)} articles")

        category_bundles = defaultdict(list)
        for article in scored_articles:
            category = article.get("category", "general")
            category_bundles[category].append(article)

        for category, category_articles in category_bundles.items():
            category_articles.sort(
                key=lambda x: x.get("relevance_score", 0), reverse=True
            )
            # Limit to top 25 articles per category for the bundle (increased from 20)
            category_bundles[category] = category_articles[:25]

        print(
            f"🎯 Final news bundle ready: {sum(len(a) for a in category_bundles.values())} articles"
        )
        for category, category_articles in category_bundles.items():
            print(f"   {category.upper()}: {len(category_articles)} articles")

        return dict(category_bundles)

    def fetch_daily_news_bundle(self, user_preferences: Dict) -> Dict[str, List[Dict]]:
        """
        Fetch and process a daily news bundle for a user.

        Args:
            user_preferences: Dictionary containing user profile data.

        Returns:
            Dictionary of news articles grouped by category.
        """
        user_locale = user_preferences.get("locale", "US")
        user_language = user_preferences.get("language", "en")
        user_city = user_preferences.get("city", "")
        user_interests = user_preferences.get("interests", [])

        print(f"📡 Fetching global news bundle for user preferences:")
        print(f"   🌍 Locale: {user_locale} | 🗣️  Language: {user_language}")
        print(f"   🎯 Interests: {user_interests} | 🏙️  City: {user_city}")

        raw_articles = []

        # Fetch from Guardian
        main_categories = [i for i in user_interests if isinstance(i, str)]
        categories_to_fetch = list(set(main_categories))
        if categories_to_fetch and self.api_keys["guardian"]:
            print("🔄 Fetching from The Guardian...")
            guardian_articles = self._fetch_guardian_articles(
                categories_to_fetch, user_locale
            )
            raw_articles.extend(guardian_articles)

        # Fetch from RSS
        print("🔄 Fetching from RSS feeds...")
        rss_articles = self._fetch_rss_articles()
        raw_articles.extend(rss_articles)

        # Reddit fetching removed
        print(f"📦 Raw articles collected: {len(raw_articles)}")

        print("⚙️  Processing articles through smart pipeline...")

        # 1. Quality Filter
        quality_filtered = [
            article
            for article in raw_articles
            if self._is_high_quality_article(article)
        ]
        print(
            f"   ✅ Quality filter: {len(quality_filtered)}/{len(raw_articles)} articles"
        )

        # 2. Deduplication
        deduplicated = self._deduplicate_articles(quality_filtered)
        print(
            f"   ✅ Deduplication: {len(deduplicated)}/{len(quality_filtered)} articles"
        )

        # 3. AI Classification (if available)
        if classify_news:
            classified = self._classify_articles(deduplicated, user_locale)
        else:
            classified = self._classify_articles_keyword_fallback(deduplicated)
        print(f"   ✅ AI Classification step completed: {len(classified)} articles")

        # 4. Prepare final bundle with relevance scoring
        final_bundle = self._prepare_news_bundle(
            classified, user_interests, user_locale
        )

        return final_bundle


# Example usage (if run directly) is kept minimal or removed for clarity in pipeline use
# if __name__ == "__main__":
#     fetcher = SmartNewsFetcher()
#     # ... test code ...
