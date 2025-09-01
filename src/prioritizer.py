# src/prioritizer.py
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from src.logging_config import get_logger

logger = get_logger(__name__)

UserInterests = List[Union[str, Dict[str, List[str]]]]

# --- утилиты ---


def sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# --- конфиг весов (можно подкрутить из ENV) ---


@dataclass
class RankerWeights:
    bias: float = float(os.getenv("RANK_BIAS", "-1.386294361"))  # logit(0.2)
    w_hint: float = float(os.getenv("RANK_W_HINT", "1.8"))  # априори от LLM
    w_conf: float = float(os.getenv("RANK_W_CONF", "1.2"))  # уверенность модели
    w_cat: float = float(os.getenv("RANK_W_CAT", "1.1"))  # интерес по категории
    w_sub: float = float(os.getenv("RANK_W_SUB", "1.6"))  # интерес по субкатегории
    w_locale: float = float(os.getenv("RANK_W_LOCALE", "0.5"))  # локаль (условный)
    w_crit: float = float(os.getenv("RANK_W_CRIT", "0.9"))  # критические слова
    gamma: float = float(os.getenv("RANK_CAL_GAMMA", "0.95"))  # калибровка хвостов


DEFAULT_WEIGHTS = RankerWeights()

# --- словарь синонимов субкатегорий ---

SYNONYMS = {
    "premier_league": "football_epl",
    "football_premier_league": "football_epl",
    "epl": "football_epl",
    "bundesliga": "football_bundesliga",
    "la_liga": "football_laliga",
}

CRITICAL_TOKENS = [
    "final",
    "game 7",
    "grand slam",
    "record",
    "all-time",
    "pandemic",
    "sanction",
    "sanctions",
    "war",
    "default",
    "ban",
    "historic",
    "emergency",
    "state of emergency",
    "evacuation",
    "championship",
]


def _norm_sub(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    v = value.lower()
    return SYNONYMS.get(v, v)


def _match_category_interest(category: str, interests: UserInterests) -> bool:
    for it in interests:
        if isinstance(it, str) and it == category:
            return True
        if isinstance(it, dict) and category in it:
            return True
    return False


def _match_sub_interest(
    category: str, sub: Optional[str], interests: UserInterests
) -> bool:
    if not sub:
        return False
    sub = _norm_sub(sub)
    for it in interests:
        if isinstance(it, dict) and category in it:
            wanted = {_norm_sub(s) for s in it[category]}
            if sub in wanted:
                return True
    return False


def _locale_match(
    reasons: str,
    news_text: Optional[str],
    user_locale: Optional[str],
    city: Optional[str],
) -> bool:
    hay = " ".join(filter(None, [reasons or "", news_text or ""])).lower()
    if user_locale and user_locale.lower() in hay:
        return True
    if city and city.lower() in hay:
        return True
    return False


def _criticality_signal(reasons: str, news_text: Optional[str]) -> bool:
    hay = " ".join(filter(None, [reasons or "", news_text or ""])).lower()
    return any(tok in hay for tok in CRITICAL_TOKENS)


# --- публичный API ---


def adjust_priority(
    classification: Dict[str, Any],
    user: Any,
    news_text: Optional[str] = None,
    weights: RankerWeights = DEFAULT_WEIGHTS,
) -> int:
    """
    Итоговый приоритет 0–100 для новости.
    Логика:
      - Глобальные важные события всегда выше
      - Локальные усиливаются только если сами по себе значимы
    """
    # 1) априори от LLM
    pr_hint_1_10 = int(classification.get("priority_llm", 5))
    p_hint = clamp((pr_hint_1_10 - 1) / 9.0, 0.01, 0.99)
    z = weights.bias + weights.w_hint * logit(p_hint)

    # 2) уверенность модели
    conf = float(classification.get("confidence", 0.7))
    z += weights.w_conf * (conf - 0.5) * 2.0

    # 3) категория в интересах
    interests: UserInterests = getattr(user, "interests", []) or []
    category: str = classification.get("category", "")
    if _match_category_interest(category, interests):
        z += weights.w_cat

    # 4) субкатегории
    sports_sub = _norm_sub(classification.get("sports_subcategory"))
    econ_sub = classification.get("economy_subcategory")
    tech_sub = classification.get("tech_subcategory")

    econ_sub = econ_sub.lower() if isinstance(econ_sub, str) else econ_sub
    tech_sub = tech_sub.lower() if isinstance(tech_sub, str) else tech_sub

    if category == "sports" and _match_sub_interest("sports", sports_sub, interests):
        z += weights.w_sub
    if category == "economy_finance" and _match_sub_interest(
        "economy_finance", econ_sub, interests
    ):
        z += weights.w_sub
    if category == "technology_ai_science" and _match_sub_interest(
        "technology_ai_science", tech_sub, interests
    ):
        z += weights.w_sub

    # 5) локаль — условный буст
    reasons = classification.get("reasons", "") or ""
    if _locale_match(
        reasons, news_text, getattr(user, "locale", None), getattr(user, "city", None)
    ):
        if conf > 0.6 or _criticality_signal(reasons, news_text):
            z += weights.w_locale  # полноценный буст для важных событий
        else:
            z += weights.w_locale * 0.2  # слабый эффект для мелких новостей

    # 6) критичность (сильные слова)
    if _criticality_signal(reasons, news_text):
        z += weights.w_crit

    # 7) вероятность → приоритет
    p = sigmoid(z)
    p_cal = p**weights.gamma
    score = int(round(100 * clamp(p_cal, 0.0, 1.0)))
    return score
