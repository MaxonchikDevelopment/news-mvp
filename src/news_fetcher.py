"""Smart News Fetcher - Custom implementation for global personalized news delivery.
   Fetches from multiple sources, handles multilingual content, and prepares for MVP.
"""

import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import requests
from dotenv import load_dotenv

load_dotenv()  # Загружает переменные из .env файла


class SmartNewsFetcher:
    """Intelligent news fetching with global coverage and smart filtering."""

    def __init__(self):
        """Initialize with all available sources and smart configuration."""
        # Debug: Print current environment variables
        print("🔍 Debug - Environment variables:")
        newsapi_key_env = os.getenv("NEWSAPI_KEY")
        guardian_key_env = os.getenv("GUARDIAN_KEY")
        reddit_client_id_env = os.getenv("REDDIT_CLIENT_ID")
        reddit_client_secret_env = os.getenv("REDDIT_CLIENT_SECRET")
        mistral_api_key_env = os.getenv("MISTRAL_API_KEY")
        print(f"   NEWSAPI_KEY: {'SET' if newsapi_key_env else 'NOT SET'}")
        print(f"   GUARDIAN_KEY: {'SET' if guardian_key_env else 'NOT SET'}")
        print(f"   REDDIT_CLIENT_ID: {'SET' if reddit_client_id_env else 'NOT SET'}")
        print(
            f"   REDDIT_CLIENT_SECRET: {'SET' if reddit_client_secret_env else 'NOT SET'}"
        )
        print(f"   MISTRAL_API_KEY: {'SET' if mistral_api_key_env else 'NOT SET'}")
        if newsapi_key_env:
            print(
                f"   NEWSAPI_KEY value: {newsapi_key_env[:4]}...{newsapi_key_env[-4:]}"
            )
        if guardian_key_env:
            print(
                f"   GUARDIAN_KEY value: {guardian_key_env[:4]}...{guardian_key_env[-4:]}"
            )
        if reddit_client_id_env:
            print(
                f"   REDDIT_CLIENT_ID value: {reddit_client_id_env[:4]}...{reddit_client_id_env[-4:]}"
            )
        if reddit_client_secret_env:
            print(
                f"   REDDIT_CLIENT_SECRET value: {reddit_client_secret_env[:4]}...{reddit_client_secret_env[-4:]}"
            )
        if mistral_api_key_env:
            print(
                f"   MISTRAL_API_KEY value: {mistral_api_key_env[:4]}...{mistral_api_key_env[-4:]}"
            )

        # Setup paths for correct imports
        current_dir = os.path.dirname(__file__)
        root_dir = os.path.dirname(current_dir)
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)
            print(f"   🔧 Added to path: {root_dir}")

        # API Keys
        self.newsapi_key = os.getenv("NEWSAPI_KEY", "")
        self.guardian_key = os.getenv("GUARDIAN_KEY", "")
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID", "")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY", "")

        # Check for optional dependencies
        self.feedparser_available = self._check_feedparser()
        self.langdetect_available = self._check_langdetect()

        # Global news sources configuration
        self.sources_config = {
            "premium": {
                "newsapi": {
                    "enabled": bool(self.newsapi_key),
                    "daily_limit": 100,  # Free tier limit
                    "categories": [
                        "business",
                        "sports",
                        "technology",
                        "general",
                        "health",
                        "science",
                        "entertainment",
                    ],
                },
                "guardian": {
                    "enabled": bool(self.guardian_key),
                    "daily_limit": 500,  # Higher limit
                    "categories": [
                        "world",
                        "sport",
                        "technology",
                        "business",
                        "environment",
                    ],
                },
            },
            "free": {
                "rss": {
                    "enabled": self.feedparser_available,
                    "sources": self._get_global_rss_feeds(),
                },
                "reddit": {
                    "enabled": bool(
                        self.reddit_client_id and self.reddit_client_secret
                    ),
                    "subreddits": [
                        "worldnews",
                        "technology",
                        "sports",
                        "business",
                        "economics",
                    ],
                },
            },
        }

        # Content quality filters
        self.quality_filters = {
            "min_length": 150,  # Minimum characters for quality content
            "max_length": 50000,  # Maximum to avoid huge articles
            "required_fields": ["title", "description"],
            "banned_keywords": [
                "advertisement",
                "sponsored",
                "promo",
                "deal",
                "welcome",
                "rules",
                "faq",
                "introduction",
            ],
            "duplicate_threshold": 0.8,  # Similarity threshold for deduplication
        }

        # Translation support
        self.translation_enabled = True
        self.target_language = "en"  # Default target language

        print("🌍 SmartNewsFetcher initialized with global coverage")
        self._print_source_status()

    def _check_feedparser(self) -> bool:
        """Check if feedparser is available."""
        try:
            import feedparser

            return True
        except ImportError:
            print("⚠️  feedparser not installed. RSS feeds will be disabled.")
            print("   To enable RSS: pip install feedparser")
            return False

    def _check_langdetect(self) -> bool:
        """Check if langdetect is available."""
        try:
            import langdetect

            return True
        except ImportError:
            print("⚠️  langdetect not installed. Language detection will be basic.")
            print("   To enable advanced language detection: pip install langdetect")
            return False

    def _get_global_rss_feeds(self) -> Dict[str, List[str]]:
        """Get comprehensive global RSS feeds by region and language."""
        return {
            # English sources
            "en": [
                "http://feeds.bbci.co.uk/news/rss.xml",
                "https://rss.cnn.com/rss/edition.rss",
                "https://feeds.reuters.com/reuters/topNews",
                "https://www.aljazeera.com/xml/rss/all.xml",
            ],
            # German sources
            "de": [
                "https://www.tagesschau.de/xml/rss2",
                "https://www.spiegel.de/schlagzeilen/index.rss",
            ],
            # Global financial sources
            "financial": [
                "https://www.ft.com/rss/home",  # <<< TARGET RSS FEED <<<
                "https://www.economist.com/latest/rss.xml",
            ],
        }

    def _print_source_status(self):
        """Print current source configuration status."""
        print("📊 Source Configuration:")
        for tier, sources in self.sources_config.items():
            print(f"  {tier.upper()}:")
            for source, config in sources.items():
                status = "✅ ENABLED" if config["enabled"] else "❌ DISABLED"
                print(f"    {source}: {status}")

    def fetch_daily_news_bundle(self, user_preferences: Dict) -> Dict[str, List[Dict]]:
        """
        Fetch comprehensive daily news bundle with smart filtering.

        Args:
            user_preferences: User profile with locale, interests, language preferences

        Returns:
            Dictionary with categorized news articles ready for processing
        """
        user_locale = user_preferences.get("locale", "en")
        user_language = user_preferences.get("language", "en")
        user_interests = user_preferences.get("interests", [])
        user_city = user_preferences.get("city", "")

        print(f"📡 Fetching global news bundle for user preferences:")
        print(f"   🌍 Locale: {user_locale} | 🗣️  Language: {user_language}")
        print(f"   🎯 Interests: {user_interests} | 🏙️  City: {user_city}")

        # Fetch from all enabled sources
        all_articles = []

        # 1. Premium sources (limited by free tier)
        if self.sources_config["premium"]["newsapi"]["enabled"]:
            print("🔄 Fetching from NewsAPI...")
            newsapi_articles = self._fetch_newsapi_articles(user_locale, user_interests)
            all_articles.extend(newsapi_articles)
            print(f"   ✅ NewsAPI: {len(newsapi_articles)} articles")

        if self.sources_config["premium"]["guardian"]["enabled"]:
            print("🔄 Fetching from The Guardian...")
            guardian_articles = self._fetch_guardian_articles(
                user_locale, user_interests
            )
            all_articles.extend(guardian_articles)
            print(f"   ✅ Guardian: {len(guardian_articles)} articles")

        # 2. Free sources (unlimited)
        if self.sources_config["free"]["rss"]["enabled"]:
            print("🔄 Fetching from RSS feeds...")
            rss_articles = self._fetch_rss_articles(user_locale, user_language)
            all_articles.extend(rss_articles)
            print(f"   ✅ RSS: {len(rss_articles)} articles")
        else:
            print("⏭️  RSS feeds disabled (feedparser not available)")

        # 3. Reddit (if enabled)
        if self.sources_config["free"]["reddit"]["enabled"]:
            print("🔄 Fetching from Reddit...")
            reddit_articles = self._fetch_reddit_articles(user_interests)
            all_articles.extend(reddit_articles)
            print(f"   ✅ Reddit: {len(reddit_articles)} articles")

        print(f"📦 Raw articles collected: {len(all_articles)}")

        # Smart processing pipeline
        processed_articles = self._process_articles_pipeline(
            all_articles, user_preferences
        )

        # Categorize and prepare final bundle
        news_bundle = self._prepare_news_bundle(processed_articles, user_interests)

        print(
            f"🎯 Final news bundle ready: {sum(len(articles) for articles in news_bundle.values())} articles"
        )
        for category, articles in news_bundle.items():
            print(f"   {category}: {len(articles)} articles")

        return news_bundle

    def _fetch_newsapi_articles(self, locale: str, interests: List[str]) -> List[Dict]:
        """Fetch articles from NewsAPI with smart category mapping."""
        if not self.newsapi_key:
            return []

        try:
            # Map our categories to NewsAPI categories
            category_mapping = {
                "economy_finance": "business",
                "sports": "sports",
                "technology_ai_science": "technology",
                "healthcare_pharma": "health",
                "politics_geopolitics": "general",
                "energy_climate_environment": "general",
            }

            articles = []
            fetch_limit = 15  # Conservative limit for MVP

            # Fetch general news + category-specific news
            categories_to_fetch = ["general"]
            for interest in interests:
                if interest in category_mapping:
                    mapped_category = category_mapping[interest]
                    if mapped_category not in categories_to_fetch:
                        categories_to_fetch.append(mapped_category)

            for category in categories_to_fetch[
                :3
            ]:  # Limit categories to avoid quota issues
                params = {
                    "apiKey": self.newsapi_key,
                    "language": locale[:2],
                    "category": category,
                    "sortBy": "publishedAt",
                    "pageSize": min(fetch_limit, 20),
                }

                response = requests.get(
                    "https://newsapi.org/v2/top-headlines",  # Исправлено: убраны лишние пробелы
                    params=params,
                    timeout=15,
                )
                response.raise_for_status()

                data = response.json()
                category_articles = data.get("articles", [])

                for article in category_articles:
                    if article.get("title") and article.get("description"):
                        # Skip articles with banned keywords
                        title = article["title"].lower()
                        if any(
                            keyword in title
                            for keyword in self.quality_filters["banned_keywords"]
                        ):
                            continue

                        processed_article = {
                            "title": article["title"],
                            "description": article["description"],
                            "content": f"{article['title']}\n\n{article['description']}\n\n{article.get('content', '')}",
                            "url": article["url"],
                            "published_at": article["publishedAt"],
                            "source": article.get("source", {}).get("name", "NewsAPI"),
                            "category": "general",  # Will be classified by AI
                            "language": locale[:2],
                            "original_language": locale[:2],
                            "relevance_score": 0.5,  # Will be calculated later
                            "ai_classified": False,
                        }
                        articles.append(processed_article)

            return articles

        except Exception as e:
            print(f"⚠️  NewsAPI fetch error: {e}")
            return []

    def _fetch_guardian_articles(self, locale: str, interests: List[str]) -> List[Dict]:
        """Fetch articles from The Guardian API."""
        if not self.guardian_key:
            return []

        try:
            params = {
                "api-key": self.guardian_key,
                "page-size": 20,
                "order-by": "newest",
                "show-fields": "headline,trailText,body,byline",
                "from-date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                # Убираем параметр 'lang' - Guardian API его не поддерживает
            }

            response = requests.get(
                "https://content.guardianapis.com/search",  # Исправлено: убраны лишние пробелы
                params=params,
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("response", {}).get("results", [])

            print(f"   📊 Guardian API response: {len(results)} total articles")

            articles = []
            for article in results:
                fields = article.get("fields", {})
                if (
                    fields.get("headline")
                    and fields.get("trailText")
                    and fields["headline"].strip()
                    and fields["trailText"].strip()
                ):
                    # Skip articles with banned keywords
                    title = fields["headline"].lower()
                    if any(
                        keyword in title
                        for keyword in self.quality_filters["banned_keywords"]
                    ):
                        continue

                    processed_article = {
                        "title": fields["headline"],
                        "description": fields["trailText"],
                        "content": f"{fields['headline']}\n\n{fields['trailText']}\n\n{fields.get('body', '')}",
                        "url": article["webUrl"],
                        "published_at": article["webPublicationDate"],
                        "source": "The Guardian",
                        "category": "general",  # Will be classified by AI
                        "language": "en",
                        "original_language": "en",
                        "relevance_score": 0.5,
                        "ai_classified": False,
                    }
                    articles.append(processed_article)

            print(f"   ✅ Guardian: {len(articles)} valid articles after filtering")
            return articles

        except Exception as e:
            print(f"⚠️  Guardian fetch error: {e}")
            # Добавим отладочную информацию
            try:
                error_data = response.json() if "response" in locals() else {}
                print(f"   🐛 Guardian API error details: {error_data}")
            except:
                pass
            return []

    def _fetch_rss_articles(self, locale: str, target_language: str) -> List[Dict]:
        """Fetch articles from global RSS feeds."""
        # Double-check that feedparser is available
        if not self.feedparser_available:
            return []

        try:
            import feedparser

            # Get relevant RSS feeds
            rss_feeds = self.sources_config["free"]["rss"]["sources"]

            # Select feeds based on locale and target language
            selected_feeds = []
            if locale[:2] in rss_feeds:
                selected_feeds.extend(rss_feeds[locale[:2]])
            if target_language in rss_feeds:
                selected_feeds.extend(rss_feeds[target_language])
            if "en" in rss_feeds:
                selected_feeds.extend(rss_feeds["en"][:3])  # Top English feeds
            if "financial" in rss_feeds:
                selected_feeds.extend(rss_feeds["financial"][:2])  # Financial feeds

            # Remove duplicates and limit
            selected_feeds = list(set(selected_feeds))[:6]  # Limit to 6 feeds for MVP

            articles = []
            for feed_url in selected_feeds:
                try:
                    feed = feedparser.parse(feed_url)
                    # Take top 3 articles from each feed
                    for entry in feed.entries[:3]:
                        if hasattr(entry, "title") and hasattr(entry, "summary"):
                            # Skip articles with banned keywords
                            title = entry.title.lower() if entry.title else ""
                            if any(
                                keyword in title
                                for keyword in self.quality_filters["banned_keywords"]
                            ):
                                continue

                            # Detect language
                            article_language = self._detect_language(entry.title)

                            processed_article = {
                                "title": entry.title,
                                "description": entry.summary,
                                "content": f"{entry.title}\n\n{entry.summary}",
                                "url": entry.link,
                                "published_at": entry.get(
                                    "published", datetime.now().isoformat()
                                ),
                                "source": feed.feed.get("title", "RSS Feed"),
                                "category": "general",  # Will be classified by AI
                                "language": article_language,
                                "original_language": article_language,
                                "relevance_score": 0.3,  # Lower initial score
                                "ai_classified": False,
                            }
                            articles.append(processed_article)

                except Exception as e:
                    print(f"⚠️  RSS feed error ({feed_url[:50]}...): {e}")
                    continue

            return articles

        except Exception as e:
            print(f"⚠️  RSS fetching error: {e}")
            return []

    def _fetch_reddit_articles(self, interests: List[str]) -> List[Dict]:
        """Fetch relevant articles from Reddit."""
        if not (self.reddit_client_id and self.reddit_client_secret):
            return []

        try:
            # Get access token
            auth = requests.auth.HTTPBasicAuth(
                self.reddit_client_id, self.reddit_client_secret
            )
            data = {"grant_type": "client_credentials"}
            headers = {"User-Agent": "NewsFetcher/1.0"}

            res = requests.post(
                "https://www.reddit.com/api/v1/access_token",  # Исправлено: убраны лишние пробелы
                auth=auth,
                data=data,
                headers=headers,
            )
            token = res.json().get("access_token")

            if not token:
                return []

            headers["Authorization"] = f"bearer {token}"

            articles = []
            subreddits = self.sources_config["free"]["reddit"]["subreddits"]

            for subreddit in subreddits[:3]:  # Limit subreddits
                try:
                    response = requests.get(
                        f"https://oauth.reddit.com/r/{subreddit}/hot",  # Исправлено: убраны лишние пробелы
                        headers=headers,
                        params={"limit": 5},
                    )

                    if response.status_code == 200:
                        data = response.json()
                        for post in data["data"]["children"][:3]:
                            post_data = post["data"]
                            if post_data.get("title") and post_data.get("selftext"):
                                # Skip system posts and posts with banned keywords
                                title = post_data["title"].lower()
                                if any(
                                    keyword in title
                                    for keyword in self.quality_filters[
                                        "banned_keywords"
                                    ]
                                ):
                                    continue

                                # Skip posts with very low content
                                if len(post_data["selftext"]) < 50:
                                    continue

                                processed_article = {
                                    "title": post_data["title"],
                                    "description": post_data["selftext"][:200] + "...",
                                    "content": f"{post_data['title']}\n\n{post_data['selftext']}",
                                    "url": f"https://reddit.com{post_data['permalink']}",
                                    "published_at": datetime.fromtimestamp(
                                        post_data["created_utc"]
                                    ).isoformat(),
                                    "source": f"Reddit /r/{subreddit}",
                                    "category": "general",  # Will be classified by AI
                                    "language": "en",
                                    "original_language": "en",
                                    "relevance_score": 0.4,
                                    "upvotes": post_data.get("ups", 0),
                                    "ai_classified": False,
                                }
                                articles.append(processed_article)

                except Exception as e:
                    print(f"⚠️  Reddit fetch error (r/{subreddit}): {e}")
                    continue

            return articles

        except Exception as e:
            print(f"⚠️  Reddit authentication error: {e}")
            return []

    def _detect_language(self, text: str) -> str:
        """Simple language detection."""
        # If langdetect is available, use it
        if self.langdetect_available:
            try:
                import langdetect

                return langdetect.detect(text[:100])
            except:
                pass

        # Simple fallback detection
        text_lower = text.lower()
        if any(word in text_lower for word in ["der", "die", "das", "und", "ist"]):
            return "de"
        elif any(word in text_lower for word in ["the", "and", "is", "are"]):
            return "en"
        else:
            return "en"  # Default to English

    def _process_articles_pipeline(
        self, articles: List[Dict], user_preferences: Dict
    ) -> List[Dict]:
        """Smart processing pipeline for articles."""
        print("⚙️  Processing articles through smart pipeline...")

        # 1. Quality filtering
        quality_filtered = self._filter_quality_articles(articles)
        print(f"   ✅ Quality filter: {len(quality_filtered)}/{len(articles)} articles")

        # 2. Deduplication
        deduplicated = self._deduplicate_articles(quality_filtered)
        print(
            f"   ✅ Deduplication: {len(deduplicated)}/{len(quality_filtered)} articles"
        )

        # 3. AI Classification - принудительный вызов с отладкой
        print("🔍 FORCING AI classification call...")
        try:
            ai_classified = self._classify_articles_with_ai(deduplicated)
            print(f"   ✅ AI Classification returned: {len(ai_classified)} articles")
        except Exception as e:
            print(f"   ❌ AI Classification failed: {e}")
            import traceback

            traceback.print_exc()
            # fallback to original articles
            ai_classified = deduplicated
        print(f"   ✅ AI Classification step completed: {len(ai_classified)} articles")

        # 4. Relevance scoring
        scored = self._score_article_relevance(ai_classified, user_preferences)
        print(f"   ✅ Relevance scoring: {len(scored)} articles")

        # 5. Translation using Mistral
        translated = self._translate_articles_with_mistral(scored, user_preferences)
        print(f"   ✅ Translation: {len(translated)} articles")

        # Sort by relevance score
        final_articles = sorted(
            translated, key=lambda x: x.get("relevance_score", 0), reverse=True
        )

        return final_articles[:50]  # Limit to 50 best articles for MVP

    def _filter_quality_articles(self, articles: List[Dict]) -> List[Dict]:
        """Filter articles based on quality criteria."""
        filtered = []
        for article in articles:
            content = article.get("content", "")
            title = article.get("title", "")

            # Check minimum requirements
            if (
                len(content) >= self.quality_filters["min_length"]
                and len(content) <= self.quality_filters["max_length"]
                and title
                and not any(
                    keyword in content.lower()
                    for keyword in self.quality_filters["banned_keywords"]
                )
                and not any(
                    keyword in title.lower()
                    for keyword in self.quality_filters["banned_keywords"]
                )
            ):
                filtered.append(article)

        return filtered

    def _deduplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate or very similar articles."""
        unique_articles = []
        seen_titles = set()
        seen_hashes = set()

        for article in articles:
            title = article["title"].lower().strip()
            content_hash = hashlib.md5(article["content"][:200].encode()).hexdigest()

            # Check for duplicates
            if (
                title not in seen_titles
                and content_hash not in seen_hashes
                and len(title) > 15
            ):  # Avoid very short titles
                seen_titles.add(title)
                seen_hashes.add(content_hash)
                unique_articles.append(article)

        return unique_articles

    def _classify_articles_with_ai(self, articles: List[Dict]) -> List[Dict]:
        """Use your proven AI classifier for accurate categorization."""
        print("🧠 Classifying articles with AI... ENTERING METHOD")
        try:
            # Import your classifier
            print("   🔍 Importing classifier module...")
            # Добавим отладку путей
            import sys

            print(
                f"   🔍 Current sys.path: {[p for p in sys.path if 'news' in p.lower() or 'src' in p.lower()]}"
            )
            # Попробуем импортировать по-разному
            try:
                import classifier

                print("   ✅ Imported classifier as module")
                classify_news = classifier.classify_news
            except ImportError as ie1:
                print(f"   ⚠️  Failed to import classifier as module: {ie1}")
                try:
                    from classifier import classify_news

                    print("   ✅ Imported classify_news directly")
                except ImportError as ie2:
                    print(f"   ❌ Failed to import classify_news directly: {ie2}")
                    raise ie2 from ie1  # Перебрасываем внутреннее исключение

            print("   ✅ Classifier module/function imported successfully")
            classified_articles = []
            success_count = 0

            for i, article in enumerate(articles):
                try:
                    # Prepare text for classification
                    article_text = f"{article.get('title', '')}\n\n{article.get('description', '')}"
                    print(f"   📝 Classifying article {i+1}: {article_text[:50]}...")

                    # Use your classifier
                    classification = classify_news(article_text)
                    print(f"   🎯 Classification result: {classification}")

                    # Enrich article with classification results
                    article["category"] = classification["category"]
                    article["confidence"] = classification["confidence"]
                    article["classification_reasons"] = classification["reasons"]

                    # Handle new importance_score field correctly
                    if "importance_score" in classification:
                        article["importance_score"] = classification["importance_score"]
                        # Convert 0-100 to 1-10 scale for compatibility with existing logic
                        article["priority_hint"] = max(
                            1, min(10, classification["importance_score"] // 10)
                        )
                    else:
                        # Fallback for older classifiers or if field is missing
                        article["importance_score"] = (
                            classification.get("priority_llm", 50) * 10
                        )  # Scale 1-10 to 10-100
                        article["priority_hint"] = classification.get("priority_llm", 5)

                    article["ai_classified"] = True

                    # Add contextual factors if available
                    if "contextual_factors" in classification:
                        article["contextual_factors"] = classification[
                            "contextual_factors"
                        ]

                    # Add subcategories if available
                    if classification.get("sports_subcategory"):
                        article["subcategory"] = classification["sports_subcategory"]
                    elif classification.get("economy_subcategory"):
                        article["subcategory"] = classification["economy_subcategory"]
                    elif classification.get("tech_subcategory"):
                        article["subcategory"] = classification["tech_subcategory"]

                    classified_articles.append(article)
                    success_count += 1
                    print(f"   ✅ Article {i+1} classified as {article['category']}")

                except Exception as e:
                    print(f"   ⚠️  AI classification failed for article {i+1}: {e}")
                    import traceback

                    traceback.print_exc()
                    # Keep original article with fallback classification
                    # Ensure fallback fields are present
                    if "priority_hint" not in article:
                        article["priority_hint"] = 5
                    if "importance_score" not in article:
                        article["importance_score"] = 50
                    if "ai_classified" not in article:
                        article["ai_classified"] = False
                    classified_articles.append(article)

            print(f"   ✅ AI classified {success_count}/{len(articles)} articles")
            return classified_articles

        except ImportError as e:
            print(f"⚠️  AI classifier not available (ImportError): {e}")
            import traceback

            traceback.print_exc()
            print("   Falling back to keyword-based classification...")
            # Fallback to keyword-based classification
            return self._classify_articles_with_keywords(articles)
        except Exception as e:
            print(f"⚠️  AI classification error (Other Exception): {e}")
            import traceback

            traceback.print_exc()
            # В случае другой ошибки тоже возвращаем результат keyword-классификации
            print("   Falling back to keyword-based classification due to error...")
            return self._classify_articles_with_keywords(articles)

    def _classify_articles_with_keywords(self, articles: List[Dict]) -> List[Dict]:
        """Fallback keyword-based classification."""
        print("🔤 Using keyword-based classification as fallback...")

        for article in articles:
            if not article.get("ai_classified", False):
                # Use existing keyword-based categorization
                category = self._categorize_article_by_keywords(article)
                article["category"] = category
                article["confidence"] = 0.7  # Default confidence for keyword method
                article["ai_classified"] = False
                # Ensure fallback fields are present
                if "priority_hint" not in article:
                    article["priority_hint"] = 5
                if "importance_score" not in article:
                    article["importance_score"] = 50

        return articles

    def _categorize_article_by_keywords(self, article: Dict) -> str:
        """Smart categorization of articles by keywords (fallback method)."""
        title = article.get("title", "").lower()
        description = article.get("description", "").lower()
        content = (title + " " + description)[:1000].lower()

        # Category keywords mapping with improved specificity
        category_keywords = {
            "sports": [
                "sport",
                "game",
                "match",
                "player",
                "team",
                "championship",
                "nba",
                "football",
                "soccer",
                "basketball",
                "formula1",
                "olympic",
                "world cup",
                "premier league",
                "epl",
                "bundesliga",
                "champions league",
                "final",
                "quarterback",
                "pitcher",
                "goal",
                "touchdown",
            ],
            "economy_finance": [
                "economy",
                "finance",
                "market",
                "stock",
                "bank",
                "interest rate",
                "inflation",
                "gdp",
                "financial",
                "trading",
                "investment",
                "recession",
                "deficit",
                "budget",
                "fiscal",
                "monetary",
                "currency",
                "exchange rate",
                "bond",
                "dividend",
                "earnings",
                "profit",
                "revenue",
                "ceo",
                "corporate",
                "merger",
                "acquisition",
                "ipo",
                "shares",
            ],
            "technology_ai_science": [
                "technology",
                "tech",
                "ai",
                "artificial intelligence",
                "science",
                "research",
                "innovation",
                "chip",
                "processor",
                "nvidia",
                "huawei",
                "semiconductor",
                "software",
                "hardware",
                "algorithm",
                "machine learning",
                "deep learning",
                "neural network",
                "quantum",
                "blockchain",
                "cryptocurrency",
                "digital",
                "app",
                "smartphone",
                "computer",
                "robot",
                "automation",
                "cloud",
                "data",
                "cybersecurity",
                "hacker",
                "programming",
                "developer",
                "engineer",
            ],
            "politics_geopolitics": [
                "politics",
                "government",
                "election",
                "policy",
                "international",
                "diplomatic",
                "president",
                "minister",
                "senator",
                "congress",
                "parliament",
                "democrat",
                "republican",
                "prime minister",
                "diplomat",
                "embassy",
                "treaty",
                "sanction",
                "alliance",
                "conflict",
                "war",
                "peace",
                "vote",
                "legislation",
                "law",
                "court",
                "supreme court",
                "constitution",
            ],
            "energy_climate_environment": [
                "energy",
                "climate",
                "environment",
                "sustainability",
                "renewable",
                "carbon",
                "oil",
                "gas",
                "solar",
                "wind",
                "nuclear",
                "coal",
                "emission",
                "pollution",
                "recycling",
                "greenhouse",
                "temperature",
                "weather",
                "disaster",
                "flood",
                "hurricane",
                "earthquake",
                "wildfire",
                "conservation",
                "ecosystem",
                "biodiversity",
                "forest",
                "ocean",
                "sea level",
            ],
            "healthcare_pharma": [
                "health",
                "medical",
                "hospital",
                "doctor",
                "pharma",
                "drug",
                "treatment",
                "vaccine",
                "medicine",
                "patient",
                "disease",
                "virus",
                "covid",
                "pandemic",
                "epidemic",
                "therapy",
                "surgery",
                "clinical",
                "trial",
                "fda",
                "fda approval",
                "symptom",
                "diagnosis",
                "cure",
                "wellness",
                "fitness",
                "nutrition",
                "diet",
                "mental health",
                "psychology",
            ],
        }

        # Find best matching category
        best_category = "general"
        best_score = 0

        for category, keywords in category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in content)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    def _score_article_relevance(
        self, articles: List[Dict], user_preferences: Dict
    ) -> List[Dict]:
        """Score articles based on user preferences and relevance with enhanced tech weighting."""
        user_interests = user_preferences.get("interests", [])
        user_locale = user_preferences.get("locale", "en")
        user_city = user_preferences.get("city", "")

        # Flatten user interests for easier matching (including nested dicts like sports subcategories)
        flat_user_interests = []
        for interest in user_preferences.get("interests", []):
            if isinstance(interest, str):
                flat_user_interests.append(interest)
            elif isinstance(interest, dict):
                flat_user_interests.extend(interest.keys())  # e.g., 'sports'
                # Optionally, you could also add subcategories like 'basketball_nba' if needed for finer control

        for article in articles:
            score = 0.5  # Base score

            # --- Interest Matching ---
            article_category = article.get("category", "general")
            ai_confidence = article.get("confidence", 0.7)

            if article_category in flat_user_interests:
                # Boost score based on AI confidence
                score += 0.3 * ai_confidence
            else:
                # Slight penalty for non-interest categories, scaled by confidence
                score -= 0.1 * (1 - ai_confidence)

            # --- Enhanced Technology Scoring ---
            # Check for high-importance technology topics
            is_tech = article_category == "technology_ai_science"
            importance_score = article.get(
                "importance_score", 50
            )  # 0-100 scale from new classifier

            if is_tech and importance_score >= 85:
                # Significant boost for highly important tech news (e.g., geopolitical chip races, major AI breakthroughs)
                score += 0.3
                print(
                    f"   🔧 Boosting high-importance tech article ({article.get('title', '')[:30]}...): +0.30 (Score now {score:.2f})"
                )
            elif is_tech and importance_score >= 75:
                # Moderate boost for important tech news
                score += 0.2
                print(
                    f"   🔩 Boosting important tech article ({article.get('title', '')[:30]}...): +0.20 (Score now {score:.2f})"
                )
            elif is_tech and importance_score >= 65:
                # Small boost for moderately important tech news
                score += 0.1
                print(
                    f"   🔧 Boosting moderate tech article ({article.get('title', '')[:30]}...): +0.10 (Score now {score:.2f})"
                )

            # --- Contextual Factors (from enhanced classifier) ---
            # If we have detailed contextual analysis, use it
            contextual = article.get("contextual_factors", {})
            if contextual:
                # Global Impact: 0-100 scale
                global_impact = contextual.get("global_impact", 50)
                if global_impact > 85:
                    score += 0.20
                elif global_impact > 70:
                    score += 0.15
                elif global_impact > 50:
                    score += 0.10

                # Time Sensitivity: 0-100 scale
                time_sensitivity = contextual.get("time_sensitivity", 50)
                if time_sensitivity > 85:
                    score += 0.15
                elif time_sensitivity > 70:
                    score += 0.10

                # Historical Significance for tech
                hist_sig = contextual.get("historical_significance", 50)
                if is_tech and hist_sig > 80:
                    score += 0.15
                elif is_tech and hist_sig > 60:
                    score += 0.10

            # --- Standard Factors ---
            # Locale relevance
            article_locale = article.get("language", "en")
            if article_locale == user_locale:
                score += 0.1
            elif article_locale in ["en", "de"]:  # Major languages
                score += 0.05

            # Source quality boost (weighted slightly higher)
            source = article.get("source", "").lower()
            quality_sources = [
                "guardian",
                "bbc",
                "reuters",
                "cnn",
                "bloomberg",
                "ft",
                "economist",
                "financial times",
            ]
            if any(quality_source in source for quality_source in quality_sources):
                score += 0.12  # Increased from 0.1

            # Recency boost (today's articles)
            published_str = article.get("published_at", "")
            if published_str:
                try:
                    published_date = datetime.fromisoformat(
                        published_str.replace("Z", "+00:00")
                    )
                    if published_date.date() == datetime.now().date():
                        score += 0.1
                except:
                    pass

            # --- Final Importance Score Integration ---
            # Use the new 0-100 importance score as a significant component
            # Scale it to contribute 0.0 - 0.3 to the final score
            scaled_importance_contribution = (importance_score / 100.0) * 0.3
            score += scaled_importance_contribution

            # --- Cap and Store ---
            # Ensure score is within 0.0 - 1.0
            article["relevance_score"] = min(1.0, max(0.0, score))

        return articles

    def _translate_articles_with_mistral(
        self, articles: List[Dict], user_preferences: Dict
    ) -> List[Dict]:
        """Translate articles using Mistral AI if needed."""
        target_language = user_preferences.get("language", "en")

        # Проверяем, есть ли статьи для перевода
        articles_to_translate = [
            article
            for article in articles
            if article.get("language", "en") != target_language
        ]

        if not articles_to_translate or not self.mistral_api_key:
            return articles

        print(
            f"🔤 Translating {len(articles_to_translate)} articles to {target_language} using Mistral..."
        )

        # Используем Mistral для перевода
        try:
            from mistralai import Mistral

            client = Mistral(api_key=self.mistral_api_key)

            for article in articles_to_translate:
                try:
                    original_language = article.get("language", "unknown")

                    # Ограничиваем длину текста для экономии токенов
                    title = article.get("title", "")[:200]
                    content = article.get("content", "")[:800]  # Ограничиваем для MVP

                    # Создаем промпт для перевода
                    translation_prompt = f"""
Translate the following news article from {original_language} to {target_language}.
Preserve the meaning, tone, and style. Keep all proper names and technical terms accurate.

Article to translate:
Title: {title}
Content: {content}
"""

                    response = client.chat.complete(
                        model="mistral-small-latest",  # Используем более дешевую модель для перевода
                        messages=[{"role": "user", "content": translation_prompt}],
                        max_tokens=1000,
                        temperature=0.1,  # Низкая температура для точного перевода
                    )

                    translated_text = response.choices[0].message.content

                    # Парсим переведенный текст
                    if "Title:" in translated_text and "Content:" in translated_text:
                        parts = translated_text.split("Content:", 1)
                        if len(parts) == 2:
                            title_part = parts[0].replace("Title:", "").strip()
                            content_part = parts[1].strip()
                            article["translated_title"] = title_part
                            article["translated_content"] = content_part
                    else:
                        # Если формат не распознан, используем весь текст
                        article["translated_content"] = translated_text

                    article["language"] = target_language  # Обновляем язык
                    print(f"   ✅ Translated: {title[:30]}...")

                except Exception as e:
                    print(f"   ⚠️  Translation failed for article: {e}")
                    # Оставляем оригинальный текст
                    continue

        except ImportError:
            print("⚠️  Mistral AI not available, skipping translation")
        except Exception as e:
            print(f"⚠️  Mistral translation error: {e}")

        return articles

    def _prepare_news_bundle(
        self, articles: List[Dict], user_interests: List[str]
    ) -> Dict[str, List[Dict]]:
        """Prepare final news bundle categorized by relevance."""
        bundle = defaultdict(list)

        # Categorize articles (now using AI classification)
        for article in articles:
            category = article.get("category", "general")
            bundle[category].append(article)

        # Limit each category to reasonable number
        for category in bundle:
            bundle[category] = sorted(
                bundle[category],
                key=lambda x: x.get("relevance_score", 0),
                reverse=True,
            )[
                :15
            ]  # Max 15 articles per category

        return dict(bundle)


# Test execution for MVP
if __name__ == "__main__":
    fetcher = SmartNewsFetcher()

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

    print("🚀 Testing SmartNewsFetcher with sample preferences...")
    news_bundle = fetcher.fetch_daily_news_bundle(sample_preferences)

    print(f"\n{'='*70}")
    print(f"🎯 SMART NEWS BUNDLE RESULTS")
    print(f"{'='*70}")

    total_articles = sum(len(articles) for articles in news_bundle.values())
    print(f"📊 Total articles: {total_articles}")

    for category, articles in news_bundle.items():
        print(f"\n📁 {category.upper()}: {len(articles)} articles")
        for i, article in enumerate(articles[:3]):  # Show top 3 per category
            print(f"   📰 {i+1}. {article['title'][:60]}...")
            print(
                f"      Source: {article['source']} | Score: {article.get('relevance_score', 0):.2f}"
            )
            print(
                f"      Language: {article.get('language')} → {sample_preferences['language']}"
            )
            if article.get("ai_classified"):
                print(
                    f"      AI Confidence: {article.get('confidence', 0):.2f} | Importance: {article.get('importance_score', 0)}/100"
                )
                if "contextual_factors" in article:
                    ctx = article["contextual_factors"]
                    print(
                        f"      Context: Global {ctx.get('global_impact', 'N/A')}, Time {ctx.get('time_sensitivity', 'N/A')}"
                    )
