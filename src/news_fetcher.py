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

# Import classifier module
try:
    from src.classifier import classify_news

    CLASSIFIER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Classifier module not available: {e}")
    CLASSIFIER_AVAILABLE = False
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
            "min_length": 100,  # Slightly increased minimum length for better content
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

            # Increase page size to get more articles
            params = {
                "api-key": self.api_keys["guardian"],
                "section": guardian_section,
                "from-date": yesterday,
                "to-date": yesterday,
                "page-size": 15,  # Increased from 10
                "show-fields": "headline,trailText,body",
                "order-by": "relevance",
            }

            try:
                response = requests.get(guardian_url, params=params, timeout=15)
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
                        "category": user_category,  # Keep user's category name
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

    def _parse_rss_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse various RSS date formats to datetime object."""
        if not date_str:
            return None
        # Common formats (add more if needed)
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822 (e.g., Wed, 02 Oct 2002 15:00:00 +0200)
            "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC (e.g., 2002-10-02T15:00:00Z)
            "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone (e.g., 2002-10-02T15:00:00+02:00)
            "%Y-%m-%d %H:%M:%S",  # Simple format (e.g., 2002-10-02 15:00:00)
            "%Y-%m-%d",  # Date only (e.g., 2002-10-02)
        ]
        for fmt in formats:
            try:
                # Special handling for timezone offsets like '+0100'
                if "%z" in fmt and ("+" in date_str[-5:] or "-" in date_str[-5:]):
                    # feedparser usually handles this, but let's be safe
                    parsed_date = datetime.strptime(date_str, fmt)
                else:
                    parsed_date = datetime.strptime(date_str, fmt)
                # Ensure timezone awareness
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                return parsed_date
            except ValueError:
                continue
        # If parsing fails, return None
        # print(f"  ⚠️ Could not parse date: {date_str}") # Uncomment for debugging
        return None

    def _fetch_rss_articles(self) -> List[Dict]:
        """Fetch articles from RSS feeds."""
        try:
            import feedparser
        except ImportError:
            print("⚠️ feedparser not installed. Skipping RSS feeds.")
            return []

        articles = []
        # Get today's date range for filtering (in UTC)
        now = datetime.now(timezone.utc)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = start_of_today.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        # Increase total RSS feeds processed to get more variety
        feeds_to_process = self.rss_feeds[:35]  # Increased from 25

        for url in feeds_to_process:
            try:
                clean_url = url.strip()
                if not clean_url:  # Skip empty strings
                    continue
                feed = feedparser.parse(clean_url)
                # Increase articles per feed
                entries_to_process = feed.entries[:10]  # Increased from 7

                for entry in entries_to_process:
                    published_at_raw = getattr(entry, "published", None)
                    published_at_dt = self._parse_rss_date(published_at_raw)

                    # --- NEW DATE FILTERING LOGIC ---
                    # Include article if:
                    # 1. Date is unknown/unclear (assume it's recent enough)
                    # 2. Date is within TODAY (UTC)
                    include_article = True
                    if published_at_dt:
                        # Normalize to UTC for comparison
                        entry_date_utc = published_at_dt.astimezone(timezone.utc)
                        if not (start_of_today <= entry_date_utc <= end_of_today):
                            include_article = False

                    if not include_article:
                        continue
                    # --- END NEW DATE FILTERING ---

                    article = {
                        "source": getattr(feed.feed, "title", clean_url),
                        "title": getattr(entry, "title", ""),
                        "description": getattr(entry, "summary", ""),
                        "content": getattr(entry, "content", [{}])[0].get("value", "")
                        if hasattr(entry, "content")
                        else "",
                        "url": getattr(entry, "link", ""),
                        "published_at": published_at_raw,  # Keep original string
                        "published_at_dt": published_at_dt,  # Add parsed datetime for potential later use
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
        """Check if an article meets relaxed but reasonable quality criteria."""
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
        if not CLASSIFIER_AVAILABLE or not classify_news:
            print("  ⚠️ AI classifier not available, using keyword classification")
            return self._classify_articles_keyword_fallback(articles)

        print("  🔍 FORCING AI classification call...")
        print("  🧠 Classifying articles with AI... ENTERING METHOD")

        classified_articles = []
        for i, article in enumerate(articles):
            # Improved text preparation for classification: Title + Description + start of Content
            title = article.get("title", "")
            description = article.get("description", "")
            content = article.get("content", "")

            # Prioritize content, then description, then title for text to classify
            if content:
                text_to_classify = f"{title}\n\n{description}\n\n{content[:2000]}"  # Limit content part
            elif description:
                text_to_classify = f"{title}\n\n{description}"
            else:
                text_to_classify = title

            if not text_to_classify.strip():
                # Fallback if everything is empty
                text_to_classify = title or "No title"

            try:
                classification_result = classify_news(
                    text_to_classify, user_locale=user_locale
                )

                article.update(classification_result)
                article["ai_classified"] = True
                classified_articles.append(article)
                # print(f"    ✅ Article {i+1} classified as {classification_result.get('category')}") # Minimized log

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

    def _classify_articles_keyword_fallback(self, articles: List[Dict]) -> List[Dict]:
        """Fallback classification using keywords."""
        classified_articles = []
        for article in articles:
            classification = self._classify_single_article_keyword_fallback(article)
            article.update(classification)
            article["ai_classified"] = False
            classified_articles.append(article)
        return classified_articles

    def _classify_single_article_keyword_fallback(self, article: Dict) -> Dict:
        """Classify a single article using keywords."""
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()

        # More detailed keywords, including subcategories for sports
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
                "senate",
                "ukraine",
                "russia",
                "china",
                "usa",
                "eu",
                "nato",
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
                "fed",
                "ecb",
                "interest rate",
                "unemployment",
                "layoff",
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
                "data",
                "quantum",
                "robot",
                "app",
                "digital",
                "semiconductor",
                "nvidia",
                "apple",
                "google",
                "microsoft",
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
                "nba",
                "epl",
                "premier league",
                "bundesliga",
                "formula 1",
                "f1",
                "nfl",
                "atp",
                "wta",
                "olympic",
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
                "award",
                "festival",
                "concert",
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
                "fda",
                "who",
                "mental health",
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
                "climate change",
                "sustainability",
                "electric vehicle",
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
                "realtor",
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
                "remote work",
                "layoff",
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
                "boeing",
                "airbus",
                "tesla",
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

        # Map confidence to importance score (0-100)
        importance_from_confidence = int(confidence * 70)  # Max 70 from keywords

        return {
            "category": best_category,
            "confidence": round(confidence, 2),
            "reasons": "Keyword-based classification",
            "importance_score": max(
                10, importance_from_confidence
            ),  # Minimum importance of 10
            "contextual_factors": default_contextual_factors,
        }

    def _score_article_relevance(
        self, article: Dict, user_interests: List[Any], user_locale: str
    ) -> float:
        """
        Calculate a personalized relevance score (0.0 to 1.0) for an article.
        Based on importance_score (0-100) and user preferences.
        Improved algorithm with better calibration and enhanced sports boost.
        """
        importance_score = article.get(
            "importance_score", 10
        )  # Default to 10 if missing, not 50

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
                self._score_article_relevance(article, user_interests, user_locale)
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
        if CLASSIFIER_AVAILABLE and classify_news:
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
