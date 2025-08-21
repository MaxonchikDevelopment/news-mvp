"""Entry point for the news-mvp project."""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.classifier import classify_news
from src.prioritizer import adjust_priority
from src.summarizer import summarize_news
from src.user_profile import get_user_profile


def main() -> None:
    """Run the news summarizer/classifier with a sample input."""

    user = get_user_profile("test_user")

    news_samples = [
        "Federal Reserve cuts interest rates by 0.5% to stimulate the economy.",
        "NVIDIA unveils a breakthrough AI chip with 2x performance for data centers.",
        "New York Knicks advance to NBA Finals for the first time in 25 years.",
        "OPEC announces production cuts, pushing oil prices higher globally.",
        "Google launches AI-powered translation earbuds in 40 languages.",
        "President Biden signs $500B infrastructure bill into law.",
        "Apple reports record $120B quarterly revenue, driven by iPhone sales.",
        "Lionel Messi scores hat-trick in MLS debut for Inter Miami.",
        "Severe floods hit Bangladesh, leaving thousands displaced.",
        "Berlin mayor opens new local art museum in city center.",
    ]

    for news in news_samples:
        classification = classify_news(news, user_locale=user.locale)
        final_priority = adjust_priority(classification, user)

        print("=" * 80)
        print(f"News: {news}")
        print(f"Category: {classification['category']}")
        if classification["sports_subcategory"]:
            print(f"Sports subcategory: {classification['sports_subcategory']}")
        print(f"Confidence: {classification['confidence']:.2f}")
        print(f"Reasons: {classification['reasons']}")
        print(f"LLM priority: {classification['priority_llm']}")
        print(f"Final priority (adjusted for {user.user_id}): {final_priority}")


if __name__ == "__main__":
    main()
