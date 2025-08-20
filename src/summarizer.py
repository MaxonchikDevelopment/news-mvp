"""Summarizer module for processing news with prompts."""

from src.prompts import PROMPT
from src.utils import clean_text


def summarize_news(news: str) -> str:
    """Summarize a given news item using the predefined prompt.

    Args:
        news (str): The raw news text.

    Returns:
        str: Summary text based on the prompt and input news.
    """
    cleaned_news = clean_text(news)
    # Placeholder logic — here you will connect to Mistral/Ollama later
    return cleaned_news