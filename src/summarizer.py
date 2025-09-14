# src/summarizer.py
"""Summarizer module for processing news with prompts."""

import time  # Added for retry backoff

from mistralai import Mistral  # Import main client

from src.config import MISTRAL_API_KEY
from src.impacts import CATEGORY_IMPACT_MAP
from src.logging_config import get_logger

# Import all specific YNK prompts
from src.prompts import YNK_PROMPT_GENERAL, YNK_PROMPT_SPORTS, YNK_PROMPT_TECH
from src.utils import clean_text

# --- Опциональный импорт исключения ---
# Мы не импортируем MistralAPIException напрямую, так как он может отсутствовать
# в некоторых версиях SDK. Вместо этого будем проверять атрибут status_code.


logger = get_logger(__name__)


# --- Обновлённая логика повторных попыток ---
def _retry_with_backoff(func, *args, max_retries=4, base_delay=1.0, **kwargs):
    """
    Retries a function call with exponential backoff upon receiving a 429 error.

    Args:
        func: The function to call.
        args: Positional arguments for the function.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        kwargs: Keyword arguments for the function.

    Returns:
        The result of the function call.

    Raises:
        Exception: The last exception encountered if all retries fail.
    """
    # Определяем код ошибки "Rate Limited"
    RATE_LIMIT_ERROR_CODE = 429

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # --- Проверка на ошибку Rate Limit ---
            # Проверяем, есть ли у исключения атрибут status_code и равен ли он 429
            # Это работает как для MistralAPIException, так и для других типов исключений,
            # которые могут содержать этот атрибут (например, в старых/новых версиях SDK)
            is_rate_limit_error = (
                hasattr(e, "status_code") and e.status_code == RATE_LIMIT_ERROR_CODE
            )
            # --- Конец проверки ---

            if is_rate_limit_error and attempt < max_retries:
                delay = base_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    f"Rate limit ({RATE_LIMIT_ERROR_CODE}) encountered. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            else:
                # If it's not a 429, or we've exhausted retries, re-log and re-raise the original exception
                if is_rate_limit_error:
                    logger.error(
                        f"API call failed after {max_retries} retries due to rate limiting: {e}"
                    )
                else:
                    # Проверим, не является ли это ошибкой аутентификации (частая проблема)
                    auth_error_indicators = [
                        "401",
                        "Unauthorized",
                        "invalid_api_key",
                        "authentication",
                    ]
                    error_message_lower = str(e).lower()
                    if any(
                        indicator in error_message_lower
                        for indicator in auth_error_indicators
                    ):
                        logger.error(
                            f"Authentication error likely: {e}. Check MISTRAL_API_KEY."
                        )
                    else:
                        logger.error(
                            f"Non-retryable error or retries exhausted in API call: {e}"
                        )
                raise e  # Re-raise the original exception
    # Этот случай маловероятен из-за `raise e` выше, но добавлен для полноты картины
    raise Exception("Retry logic failed unexpectedly in _retry_with_backoff.")


# --- Основная функция суммаризации ---
def summarize_news(news: str, category: str) -> str:
    """
    Summarize a given news article using Mistral API.
    Selects the prompt based on the article category.

    Args:
        news (str): Raw news text.
        category (str): Category from classifier (e.g., 'sports', 'technology_ai_science').

    Returns:
        str: Summarized news text (YNK format).
    """
    logger.debug(f"Raw news (first 100 chars): {news[:100]}...")
    logger.debug(f"Category for summarization: {category}")

    client = Mistral(api_key=MISTRAL_API_KEY)
    cleaned_news = clean_text(news)

    # --- Select prompt based on category ---
    if category == "technology_ai_science":
        # Use the specialized prompt for Technology/AI/Science
        prompt = YNK_PROMPT_TECH
        logger.debug("Using YNK_PROMPT_TECH for technology_ai_science")
    elif category == "sports":
        # Use the specialized prompt for Sports
        prompt = YNK_PROMPT_SPORTS
        logger.debug("Using YNK_PROMPT_SPORTS for sports")
    else:
        # Use the general prompt for all other categories
        base_prompt = YNK_PROMPT_GENERAL
        # Get the dynamic list of impact aspects for the category
        aspects = CATEGORY_IMPACT_MAP.get(category, ["General Impact"])
        aspects_str = "\n".join([f"- {a}: ..." for a in aspects])
        # Inject the aspects into the general prompt
        prompt = base_prompt.replace("IMPACT ASPECTS", aspects_str)
        logger.debug(f"Using YNK_PROMPT_GENERAL with aspects: {aspects}")

    logger.debug(f"Final prompt used (first 200 chars):\n{prompt[:200]}...")

    try:
        # Wrap the API call with retry logic
        def _make_api_call():
            return client.chat.complete(
                model="mistral-small-latest",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": cleaned_news},
                ],
                # Limit output length to save tokens and for conciseness
                max_tokens=250,
                # Low temperature for factual, consistent output
                temperature=0.2,
            )

        response = _retry_with_backoff(_make_api_call)

        result = response.choices[0].message.content.strip()

        logger.debug(f"Generated summary (first 150 chars): {result[:150]}...")
        return result

    except Exception as e:  # Этот except ловит ошибки из _retry_with_backoff
        error_msg = f"Summary generation failed after retries: {e}"
        logger.error(error_msg)
        # Return the error message as the summary so the pipeline doesn't break
        return error_msg
