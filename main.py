"""Entry point for the news-mvp project."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from src.summarizer import summarize_news

def main() -> None:
    """Run the news summarizer with a sample input."""
    news = """Fed raises interest rates by 0.25% amid inflation concerns."""
    result = summarize_news(news)
    print(result)

if __name__ == "__main__":
    main()