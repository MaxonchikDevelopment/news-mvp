"""Summarizer module for processing news with prompts."""

from mistralai import Mistral
from src.config import MISTRAL_API_KEY
from src.prompts import PROMPT
from src.utils import clean_text


def summarize_news(news: str) -> str:
    """Summarize a given news article using Mistral API.

    Args:
        news (str): Raw news text.

    Returns:
        str: Summarized news text.
    """
    client = Mistral(api_key=MISTRAL_API_KEY)
    cleaned_news = clean_text(news)

    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": cleaned_news},
        ],
    )

    return response.choices[0].message.content