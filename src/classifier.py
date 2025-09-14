# src/classifier.py
"""News classifier with category detection and priority assessment."""

from __future__ import annotations

import json
import os
import sys
import time  # Added for retry backoff
from datetime import datetime
from typing import Any, Dict, Literal, Optional, TypedDict, get_args

from mistralai import Mistral

# --- НЕТ ИМПОРТА MistralAPIException ---

# Setup paths for correct imports
current_dir = os.path.dirname(__file__)
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from config import MISTRAL_API_KEY
from logging_config import get_logger

# Import prompts correctly from prompts.py
from prompts import CLASSIFY_AND_PRIORITIZE_PROMPT  # Import the main prompt
from prompts import (
    ECONOMY_SUBCATEGORY_PROMPT,
    SPORTS_SUBCATEGORY_PROMPT,
    TECH_SUBCATEGORY_PROMPT,
)

logger = get_logger(__name__)

# --- Type definitions remain the same ---
Category = Literal[
    "economy_finance",
    "politics_geopolitics",
    "technology_ai_science",
    "real_estate_housing",
    "career_education_labour",
    "sports",
    "energy_climate_environment",
    "culture_media_entertainment",
    "healthcare_pharma",
    "transport_auto_aviation",
]

SportSub = Literal[
    "football_bundesliga",
    "football_epl",
    "football_laliga",
    "football_other",
    "basketball_nba",
    "basketball_euroleague",
    "american_football_nfl",
    "tennis",
    "formula1",
    "ice_hockey",
    "other_sports",
]

EconomySub = Literal[
    "central_banks",
    "corporate_earnings",
    "markets",
    "other_economy",
]

TechSub = Literal[
    "semiconductors",
    "consumer_products",
    "ai_research",
    "other_tech",
]


class ContextualFactors(TypedDict):
    time_sensitivity: int
    global_impact: int
    personal_relevance: int
    historical_significance: int
    emotional_intensity: int


class ClassifierOutput(TypedDict):
    category: Category
    sports_subcategory: Optional[SportSub]
    economy_subcategory: Optional[EconomySub]
    tech_subcategory: Optional[TechSub]
    confidence: float
    reasons: str
    importance_score: int
    contextual_factors: ContextualFactors


# --- Helper functions (_salvage_json, _normalize, _ask_subcategory) remain largely the same ---
# (Only adding retry logic to the main classify_news function)


def _salvage_json(s: str) -> Dict[str, Any]:
    """Extract JSON object from potentially malformed response."""
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return json.loads(s[start : end + 1])


def _normalize(d: Dict[str, Any]) -> ClassifierOutput:
    """Normalize and validate classifier output."""
    allowed_cat = set(get_args(Category))
    allowed_sport = set(get_args(SportSub))
    allowed_econ = set(get_args(EconomySub))
    allowed_tech = set(get_args(TechSub))

    cat = str(d.get("category", "economy_finance"))
    if cat not in allowed_cat:
        cat = "economy_finance"

    sports = d.get("sports_subcategory")
    econ = d.get("economy_subcategory")
    tech = d.get("tech_subcategory")

    if sports and sports not in allowed_sport:
        sports = "other_sports"
    if econ and econ not in allowed_econ:
        econ = "other_economy"
    if tech and tech not in allowed_tech:
        tech = "other_tech"

    try:
        conf = float(d.get("confidence", 0.7))
    except Exception:
        conf = 0.7
    conf = max(0.0, min(1.0, conf))

    try:
        imp_score = int(d.get("importance_score", 50))
    except Exception:
        imp_score = 50
    imp_score = max(0, min(100, imp_score))  # 0-100 scale

    reasons = str(d.get("reasons", "")).strip()
    words = reasons.split()
    if len(words) > 25:
        reasons = " ".join(words[:25])

    # Extract contextual factors
    contextual = d.get("contextual_factors", {})
    if not isinstance(contextual, dict):
        contextual = {}

    # Ensure all contextual factors are present with default values
    default_contextual = {
        "time_sensitivity": 50,
        "global_impact": 50,
        "personal_relevance": 50,
        "historical_significance": 50,
        "emotional_intensity": 50,
    }

    # Validate and constrain contextual factors
    validated_contextual = {}
    for key, default_value in default_contextual.items():
        try:
            value = int(contextual.get(key, default_value))
            validated_contextual[key] = max(0, min(100, value))
        except (ValueError, TypeError):
            validated_contextual[key] = default_value

    return {
        "category": cat,
        "sports_subcategory": sports,
        "economy_subcategory": econ,
        "tech_subcategory": tech,
        "confidence": conf,
        "reasons": reasons,
        "importance_score": imp_score,
        "contextual_factors": validated_contextual,
    }


def _ask_subcategory(
    client: Mistral, prompt: str, text: str, key: str
) -> Optional[str]:
    """Ask for subcategory clarification."""
    # This helper function can also benefit from retries, but for simplicity,
    # we apply retry logic primarily to the main classification call.
    # If needed, _ask_subcategory can be wrapped similarly.
    resp = client.chat.complete(
        model="mistral-small-latest",
        temperature=0.0,
        max_tokens=120,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
    except Exception:
        data = _salvage_json(raw)
    return data.get(key)


# --- Retry logic helper function (БЕЗ MistralAPIException) ---
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
                    f"Rate limit ({RATE_LIMIT_ERROR_CODE}) encountered in classifier. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            else:
                # If it's not a 429, or we've exhausted retries, re-log and re-raise the original exception
                if is_rate_limit_error:
                    logger.error(
                        f"Classifier API call failed after {max_retries} retries due to rate limiting: {e}"
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
                            f"Authentication error likely in classifier: {e}. Check MISTRAL_API_KEY."
                        )
                    else:
                        logger.error(
                            f"Non-retryable error or retries exhausted in classifier API call: {e}"
                        )
                raise e  # Re-raise the original exception
    # Этот случай маловероятен из-за `raise e` выше, но добавлен для полноты картины
    raise Exception(
        "Classifier retry logic failed unexpectedly in _retry_with_backoff."
    )


# --- Main classification function with retry ---
def classify_news(text: str, user_locale: Optional[str] = None) -> ClassifierOutput:
    """Classify news text and determine importance score with contextual analysis.

    Args:
        text: News text to classify
        user_locale: User's locale for regional relevance adjustment

    Returns:
        ClassifierOutput with category, confidence, importance score, and contextual factors
    """
    client = Mistral(api_key=MISTRAL_API_KEY)

    user_msg = (
        "Classify the following news strictly as JSON. "
        "Use the user locale ONLY to adjust regional relevance/importance.\n\n"
        f"User locale: {user_locale or 'unknown'}\n\n"
        f"Current time: {datetime.now().isoformat()}\n\n"
        f"News:\n'''\n{text.strip()}\n'''"
    )

    # Define the API call as a nested function for retry wrapper
    def _make_classification_call():
        return client.chat.complete(
            model="mistral-small-latest",
            temperature=0.0,
            max_tokens=300,  # Increased for more detailed contextual analysis
            messages=[
                {
                    "role": "system",
                    "content": CLASSIFY_AND_PRIORITIZE_PROMPT,
                },  # Use imported prompt
                {"role": "user", "content": user_msg},
            ],
        )

    try:
        # Wrap the API call with retry logic
        resp = _retry_with_backoff(_make_classification_call)

        raw = resp.choices[0].message.content.strip()
        logger.debug("Raw classifier response: %s", raw)

        try:
            data = json.loads(raw)
        except Exception:
            data = _salvage_json(raw)

        out = _normalize(data)

        # Cascade subcategory refinement (can also be wrapped if needed, but less critical)
        if out["category"] == "sports":
            sub = _ask_subcategory(
                client, SPORTS_SUBCATEGORY_PROMPT, text, "sports_subcategory"
            )
            if sub:
                out["sports_subcategory"] = sub
        elif out["category"] == "economy_finance":
            sub = _ask_subcategory(
                client, ECONOMY_SUBCATEGORY_PROMPT, text, "economy_subcategory"
            )
            if sub:
                out["economy_subcategory"] = sub
        elif out["category"] == "technology_ai_science":
            sub = _ask_subcategory(
                client, TECH_SUBCATEGORY_PROMPT, text, "tech_subcategory"
            )
            if sub:
                out["tech_subcategory"] = sub

        logger.debug("Final classification with subcategory: %s", out)
        return out

    except Exception as e:
        # Log the final error after retries are exhausted
        logger.error(f"Classification failed after retries: {e}")
        # Re-raise the exception so the calling code (e.g., news_fetcher) knows it failed
        raise e
