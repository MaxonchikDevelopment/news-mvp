"""Summarizer module for processing news with prompts."""

from mistralai import Mistral

from src.config import MISTRAL_API_KEY
from src.impacts import CATEGORY_IMPACT_MAP
from src.logging_config import get_logger
from src.prompts import YNK_PROMPT
from src.utils import clean_text

logger = get_logger(__name__)


def summarize_news(news: str, category: str) -> str:
    """Summarize a given news article using Mistral API.

    Args:
        news (str): Raw news text.
        category (str): Category from classifier.

    Returns:
        str: Summarized news text.
    """
    logger.debug(f"Raw news: {news}")
    logger.debug(f"Category for summarization: {category}")

    client = Mistral(api_key=MISTRAL_API_KEY)
    cleaned_news = clean_text(news)

    # Берем список аспектов для категории
    aspects = CATEGORY_IMPACT_MAP.get(category, ["General Impact"])
    aspects_str = "\n".join([f"- {a}: ..." for a in aspects])

    # Вставляем аспекты внутрь промта
    prompt = YNK_PROMPT.replace("IMPACT ASPECTS", aspects_str)

    logger.debug(f"Final prompt used:\n{prompt}")

    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": cleaned_news},
        ],
    )

    result = response.choices[0].message.content

    logger.debug(f"Generated summary:\n{result}")

    return result
