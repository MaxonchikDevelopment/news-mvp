"""Summarizer module for processing news with prompts."""

from mistralai import Mistral

from src.config import MISTRAL_API_KEY
from src.logging_config import get_logger
from src.prompts import YNK_PROMPT
from src.utils import clean_text

logger = get_logger(__name__)


def summarize_news(news: str) -> str:
    """Summarize a given news article using Mistral API.

    Args:
        news (str): Raw news text.

    Returns:
        str: Summarized news text.
    """
    logger.info("Received news for summarization.")
    logger.debug(f"Raw news: {news}")

    client = Mistral(api_key=MISTRAL_API_KEY)
    cleaned_news = clean_text(news)

    logger.debug(f"Cleaned news: {cleaned_news}")

    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "system", "content": YNK_PROMPT},
            {"role": "user", "content": cleaned_news},
        ],
    )

    result = response.choices[0].message.content
    formatted_result = result.replace("- ", "\n- ")

    logger.info("Summarization completed successfully.")
    logger.debug(f"Generated summary:\n{formatted_result}")

    return formatted_result
