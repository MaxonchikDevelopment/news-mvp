# src/test_critical_news.py
"""Test script to evaluate the system with predefined critical news articles."""

import os
import sys


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

from news_fetcher import SmartNewsFetcher


def create_critical_test_articles():
    """Create a list of predefined critical news articles for testing."""
    return [
        {
            "title": "China seeks to triple output of AI chips in race with the US",
            "description": "Fabrication plants serving Huawei push to increase production as US cuts off access to Nvidia's top processors",
            "content": "In a significant escalation of the global semiconductor rivalry, China has instructed its domestic chip fabrication facilities, primarily those linked to Huawei, to dramatically increase their output of artificial intelligence chips. This move comes directly in response to increasingly stringent US export controls that have effectively blocked Chinese companies from accessing cutting-edge processors developed by firms like Nvidia. The strategic push aims to reduce reliance on foreign technology and bolster China's position in the critical AI hardware sector.",
            "url": "https://www.ft.com/content/china-ai-chips",
            "published_at": "2025-08-27T09:28:55Z",
            "source": "Financial Times",
            "language": "en",
            "original_language": "en",
            "ai_classified": False,
        },
        {
            "title": "European Commission proposes emergency AI regulation framework",
            "description": "Draft legislation aims to ban 'unacceptable risk' AI applications immediately and impose strict oversight on general purpose AI models.",
            "content": "The European Commission has unveiled a sweeping draft regulation designed to govern the development and deployment of Artificial Intelligence within the EU. The proposal includes immediate bans on AI applications deemed to pose an 'unacceptable risk' to citizens' rights, such as social scoring by governments. It also introduces stringent requirements for developers of general-purpose AI models, like large language models, mandating transparency reports and adherence to EU copyright laws. The regulation, if passed, would represent the world's first comprehensive AI law.",
            "url": "https://www.reuters.com/article/eu-ai-regulation",
            "published_at": "2025-08-27T08:15:00Z",
            "source": "Reuters",
            "language": "en",
            "original_language": "en",
            "ai_classified": False,
        },
        {
            "title": "Nvidia announces breakthrough in quantum computing chip design",
            "description": "New architecture promises exponential speedup for specific optimization problems crucial to AI and materials science.",
            "content": "Semiconductor giant Nvidia Corp. revealed details of a novel chip architecture that combines classical transistor design with qubit manipulation capabilities. Early benchmarks suggest the chip could solve complex optimization problems hundreds of times faster than current systems, with profound implications for drug discovery, financial modeling, and logistics. Experts believe this hybrid approach could bring practical quantum advantage closer to reality. Shares in related tech sectors surged following the announcement.",
            "url": "https://www.bloomberg.com/news/nvidia-quantum",
            "published_at": "2025-08-27T07:00:00Z",
            "source": "Bloomberg",
            "language": "en",
            "original_language": "en",
            "ai_classified": False,
        },
        {
            "title": "Major earthquake strikes Istanbul, initial reports of casualties",
            "description": "7.2 magnitude quake hits densely populated area, triggering tsunami warning in the Marmara Sea.",
            "content": "A powerful 7.2-magnitude earthquake struck the greater Istanbul region early this morning, causing widespread damage to buildings and infrastructure. Initial reports from Turkish disaster management agencies indicate several confirmed casualties and numerous injuries, though numbers are expected to rise. The quake's epicenter was located just offshore, prompting authorities to issue a tsunami warning for coastal areas around the Marmara Sea. International aid organizations are preparing relief efforts.",
            "url": "https://www.bbc.com/news/earthquakes",
            "published_at": "2025-08-27T06:30:00Z",
            "source": "BBC News",
            "language": "en",
            "original_language": "en",
            "ai_classified": False,
        },
        {
            "title": "ECB raises interest rates by 0.5% to combat inflation surge",
            "description": "European Central Bank implements largest rate hike in over a decade amid rising energy prices and wage pressures.",
            "content": "The European Central Bank has announced a surprise 0.5 percentage point increase in its key interest rate, marking the largest single hike in over ten years. The move comes as inflation in the Eurozone continues to exceed the bank's 2% target, driven by persistent energy price increases and growing wage demands. Economists warn the aggressive tightening could tip the region into recession, while markets reacted with volatility across European stock exchanges.",
            "url": "https://www.ft.com/content/ecb-rate-hike",
            "published_at": "2025-08-27T05:00:00Z",
            "source": "Financial Times",
            "language": "en",
            "original_language": "en",
            "ai_classified": False,
        },
        {
            "title": "Tesla unveils humanoid robot prototype with advanced AI capabilities",
            "description": "Optimus Gen 2 demonstrates walking, object manipulation, and basic conversation skills at company event.",
            "content": "Elon Musk unveiled Tesla's second-generation humanoid robot, Optimus Gen 2, at the company's AI Day event. The robot showcased significant improvements in mobility, dexterity, and conversational abilities compared to its predecessor. Demonstrations included walking across uneven terrain, picking up and sorting objects, and engaging in basic dialogue with attendees. Industry analysts view this as a major step toward practical applications in manufacturing and service industries.",
            "url": "https://www.reuters.com/article/tesla-robot",
            "published_at": "2025-08-27T04:30:00Z",
            "source": "Reuters",
            "language": "en",
            "original_language": "en",
            "ai_classified": False,
        },
    ]


def run_critical_news_test():
    """Run the SmartNewsFetcher pipeline on critical test articles."""
    print("🧪 Running Critical News Test...")

    # 1. Get test articles
    test_articles = create_critical_test_articles()
    print(f"   📥 Loaded {len(test_articles)} predefined critical articles.")

    # 2. Initialize fetcher
    fetcher = SmartNewsFetcher()

    # 3. Use sample user preferences (like your Maxonchik profile)
    sample_preferences = {
        "user_id": "Maxonchik",
        "locale": "DE",  # German user in Frankfurt
        "language": "en",
        "city": "Frankfurt",
        "interests": [
            "economy_finance",
            "technology_ai_science",
            {"sports": ["basketball_nba", "football_epl", "formula1"]},
        ],
    }
    print("   🎯 Using sample user preferences:")
    print(
        f"      🌍 Locale: {sample_preferences['locale']} | 🗣️  Language: {sample_preferences['language']}"
    )
    print(f"      🏙️  City: {sample_preferences['city']}")
    print(f"      🎯 Interests: {sample_preferences['interests']}")

    # 4. Inject test articles into the pipeline
    # We simulate the part of the pipeline after fetching, going straight to processing
    print("   ⚙️  Injecting articles into processing pipeline...")

    # Mimic the internal processing steps
    # a. Quality filtering (our test articles should pass)
    quality_filtered = fetcher._filter_quality_articles(test_articles)
    print(f"   ✅ Quality filter: {len(quality_filtered)}/{len(test_articles)} articles")

    # b. Deduplication (should be none for our unique test set)
    deduplicated = fetcher._deduplicate_articles(quality_filtered)
    print(f"   ✅ Deduplication: {len(deduplicated)}/{len(quality_filtered)} articles")

    # c. AI Classification
    print("   🧠 Classifying articles with AI...")
    ai_classified = fetcher._classify_articles_with_ai(deduplicated)
    print(f"   ✅ AI Classification: {len(ai_classified)} articles")

    # d. Relevance scoring (this is where our improvements kick in)
    print("   🎯 Calculating relevance scores with enhancements...")
    scored = fetcher._score_article_relevance(ai_classified, sample_preferences)
    print(f"   ✅ Relevance scoring: {len(scored)} articles")

    # e. Translation using Mistral
    translated = fetcher._translate_articles_with_mistral(scored, sample_preferences)
    print(f"   ✅ Translation: {len(translated)} articles")

    # f. Sort by relevance score
    final_articles = sorted(
        translated, key=lambda x: x.get("relevance_score", 0), reverse=True
    )
    print(f"   📊 Sorting: Articles sorted by relevance score")

    # 5. Display Results
    print(f"\n{'='*80}")
    print(f"🎯 CRITICAL NEWS TEST RESULTS")
    print(f"{'='*80}")
    print(f"📊 Total articles: {len(final_articles)}")

    for i, article in enumerate(final_articles):
        title = article.get("title", "N/A")
        source = article.get("source", "N/A")
        score = article.get("relevance_score", 0)
        category = article.get("category", "N/A")
        confidence = article.get("confidence", 0)
        importance = article.get("importance_score", "N/A")

        print(f"\n🏆 {i+1}. {title}")
        print(f"   Source: {source} | Category: {category} | Score: {score:.2f}")
        print(f"   AI Confidence: {confidence:.2f} | Importance: {importance}")

        # Show contextual factors if available
        ctx = article.get("contextual_factors", {})
        if ctx:
            print(
                f"   Context: Global {ctx.get('global_impact', 'N/A')}, Time {ctx.get('time_sensitivity', 'N/A')}"
            )

        # Show YNotCare summary if available
        if "ynotcare_summary" in article:
            print(f"   YNotCare Summary: {article['ynotcare_summary'][:100]}...")

    print(f"\n{'='*80}")


if __name__ == "__main__":
    run_critical_news_test()
