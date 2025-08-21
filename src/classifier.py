# src/classifier.py
from __future__ import annotations

import json
from typing import Any, Dict, Literal, Optional, TypedDict, get_args

from mistralai import Mistral

from src.config import MISTRAL_API_KEY
from src.logging_config import get_logger
from src.prompts import (
    CLASSIFY_AND_PRIORITIZE_PROMPT,
    ECONOMY_SUBCATEGORY_PROMPT,
    SPORTS_SUBCATEGORY_PROMPT,
    TECH_SUBCATEGORY_PROMPT,
)

logger = get_logger(__name__)

# ---- Category and Subcategory Definitions ----

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


# ---- TypedDict for structured return type ----
class ClassifierOutput(TypedDict):
    category: Category
    sports_subcategory: Optional[SportSub]
    economy_subcategory: Optional[EconomySub]
    tech_subcategory: Optional[TechSub]
    confidence: float
    reasons: str
    priority_llm: int


# ---- Helpers ----
def _salvage_json(s: str) -> Dict[str, Any]:
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return json.loads(s[start : end + 1])


def _normalize(d: Dict[str, Any]) -> ClassifierOutput:
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

    # Validate subs
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
        pr = int(d.get("priority_llm", 5))
    except Exception:
        pr = 5
    pr = max(1, min(10, pr))

    reasons = str(d.get("reasons", "")).strip()
    words = reasons.split()
    if len(words) > 25:
        reasons = " ".join(words[:25])

    return {
        "category": cat,
        "sports_subcategory": sports,
        "economy_subcategory": econ,
        "tech_subcategory": tech,
        "confidence": conf,
        "reasons": reasons,
        "priority_llm": pr,
    }


def _ask_subcategory(
    client: Mistral, prompt: str, text: str, key: str
) -> Optional[str]:
    """Call LLM to determine subcategory (sports/econ/tech)."""
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


# ---- Main Function ----
def classify_news(text: str, user_locale: Optional[str] = None) -> ClassifierOutput:
    client = Mistral(api_key=MISTRAL_API_KEY)

    user_msg = (
        "Classify the following news strictly as JSON. "
        "Use the user locale ONLY to adjust regional relevance/priority.\n\n"
        f"User locale: {user_locale or 'unknown'}\n\n"
        f"News:\n'''\n{text.strip()}\n'''"
    )

    resp = client.chat.complete(
        model="mistral-small-latest",
        temperature=0.0,
        max_tokens=220,
        messages=[
            {"role": "system", "content": CLASSIFY_AND_PRIORITIZE_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )

    raw = resp.choices[0].message.content.strip()
    logger.debug("Raw classifier response: %s", raw)

    try:
        data = json.loads(raw)
    except Exception:
        data = _salvage_json(raw)

    out = _normalize(data)

    # ---- Cascade subcategory refinement ----
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
