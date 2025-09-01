# main.py
"""Entry point for the news-mvp project.
Run:
    python main.py
"""

import os
import sys
import traceback
from types import SimpleNamespace

# --- prepare paths so `src/` is importable ---
ROOT = os.path.dirname(__file__)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# --- imports from src ---
from classifier import classify_news
from prioritizer import adjust_priority
from summarizer import summarize_news
from user_profile import get_user_profile


# --- safe wrappers (to avoid crashes if something fails) ---
def safe_classify(news: str, user_locale=None):
    try:
        return classify_news(news, user_locale=user_locale)
    except Exception:
        traceback.print_exc()
        return {"category": "unknown", "confidence": 0.0, "priority_llm": 0}


def safe_summarize(news: str, category: str):
    try:
        return summarize_news(news, category)
    except Exception:
        traceback.print_exc()
        return "(summary failed)"


def format_priority(score: int) -> str:
    """Format numeric priority score into X/100 string."""
    try:
        s = int(score)
    except Exception:
        s = 0
    s = max(0, min(100, s))
    return f"{s}/100"


# --- main execution ---
def main():
    # load user profile (fallback to test user if missing)
    user = get_user_profile("Maxonchik")
    if not user:
        user = SimpleNamespace(
            user_id="test_user",
            interests=["economy_finance", "technology_ai_science"],
            locale="DE",
            city="Frankfurt",
            language="en",
        )

    # minimal test news sample
    news_samples = [
        """In a thrilling NBA Finals Game 7, the Miami Heat edged out the Los Angeles Lakers 112-110
        to clinch the championship. Jimmy Butler scored 35 points, including the game-winning free throws
        with just seconds left. LeBron James had a triple-double for the Lakers but missed a potential
        game-tying shot at the buzzer. The Heat’s victory marks their first championship since 2013
        and solidifies Butler’s status as one of the league’s elite players."""
    ]

    for news in news_samples:
        print("\n" + "=" * 80)

        # 1) classify news
        cls = safe_classify(news, user_locale=getattr(user, "locale", None))
        category = cls.get("category", "unknown")

        # 2) summarize news
        summary = safe_summarize(news, category)
        print(summary)

        # 3) compute final priority (YNotCare variable)
        try:
            YNotCare = adjust_priority(cls, user, news_text=news)
        except Exception:
            traceback.print_exc()
            YNotCare = 0

        # 4) output results
        print("\n" + "=" * 80)
        print(f"→ Category: {category}")
        print(f"→ LLM priority: {cls.get('priority_llm')}")
        print(f"→ Priority score: {format_priority(YNotCare)}")


if __name__ == "__main__":
    main()
