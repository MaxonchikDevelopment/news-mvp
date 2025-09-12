"""News classifier with category detection and priority assessment."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Literal, Optional, TypedDict, get_args

from mistralai import Mistral

# Setup paths for correct imports
current_dir = os.path.dirname(__file__)
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from config import MISTRAL_API_KEY
from logging_config import get_logger
from prompts import (
    ECONOMY_SUBCATEGORY_PROMPT,
    SPORTS_SUBCATEGORY_PROMPT,
    TECH_SUBCATEGORY_PROMPT,
)

logger = get_logger(__name__)

# Enhanced prompt with 100-point importance scale and contextual analysis
CLASSIFY_AND_PRIORITIZE_PROMPT = """
You are a precise, context-aware news classifier and priority evaluator. 
Your task: classify the news, assign priority, and return ONLY valid JSON.

Schema:
{
 "category": "<one of: economy_finance | politics_geopolitics | technology_ai_science | real_estate_housing | career_education_labour | sports | energy_climate_environment | culture_media_entertainment | healthcare_pharma | transport_auto_aviation>",
 "sports_subcategory": "<one of: football_bundesliga | football_epl | football_laliga | football_other | basketball_nba | basketball_euroleague | american_football_nfl | tennis | formula1 | ice_hockey | other_sports | null>",
 "confidence": <float 0..1>,
 "reasons": "<≤25 words, concise, plain>",
 "importance_score": <int 0..100>,  # 100-point importance scale
 "contextual_factors": {             # NEW: Contextual analysis
   "time_sensitivity": <int 0..100>,
   "global_impact": <int 0..100>,
   "personal_relevance": <int 0..100>,
   "historical_significance": <int 0..100>,
   "emotional_intensity": <int 0..100>
 }
}

Rules for importance_score (0-100):
- 90-100: HISTORIC/GLOBAL - pandemics, wars, unmatched records, global crises
- 80-89: MAJOR NATIONAL - central bank decisions, major elections, national emergencies  
- 70-79: SIGNIFICANT REGIONAL - state-level decisions, major corporate moves
- 60-69: NOTABLE LOCAL - city-wide impacts, important local news
- 50-59: ROUTINE INTEREST - regular sports results, quarterly reports
- 40-49: MINOR RELEVANCE - small updates, gossip
- 30-39: BACKGROUND NOISE - very minor local events
- 20-29: TRIVIAL - advertisements disguised as news
- 10-19: SPAM - clearly irrelevant content
- 0-9: JUNK - completely unrelated/offensive content

Context factors:
- GLOBAL IMPACT multiplies score by 1.5-2.0
- HISTORIC FIRST-EVER adds +15-25 points
- PERSONAL RELEVANCE (based on user locale) adds +5-15 points
- TIME SENSITIVITY (breaking news) adds +10-20 points
- EMOTIONAL INTENSITY (crisis, celebration) adds +5-10 points

Examples:
Input: "World War III declared between US and China"
Output: {"category":"politics_geopolitics","sports_subcategory":null,"confidence":0.99,"reasons":"global war declaration","importance_score":98,"contextual_factors":{"time_sensitivity":95,"global_impact":100,"personal_relevance":70,"historical_significance":100,"emotional_intensity":90}}

Input: "Local mayor opens new park in small town."
Output: {"category":"politics_geopolitics","sports_subcategory":null,"confidence":0.9,"reasons":"minor local political event","importance_score":62,"contextual_factors":{"time_sensitivity":30,"global_impact":20,"personal_relevance":60,"historical_significance":10,"emotional_intensity":25}}

Input: "Nvidia releases groundbreaking AI chip for consumer market"
Output: {"category":"technology_ai_science","sports_subcategory":null,"confidence":0.95,"reasons":"major tech breakthrough","importance_score":85,"contextual_factors":{"time_sensitivity":80,"global_impact":90,"personal_relevance":85,"historical_significance":75,"emotional_intensity":70}}

Input: "China seeks to triple output of AI chips in race with the US"
Output: {"category":"technology_ai_science","sports_subcategory":null,"confidence":0.92,"reasons":"geopolitical tech competition","importance_score":88,"contextual_factors":{"time_sensitivity":85,"global_impact":95,"personal_relevance":90,"historical_significance":80,"emotional_intensity":85}}
"""

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
    contextual_factors: ContextualFactors  # NEW: Contextual analysis


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

    resp = client.chat.complete(
        model="mistral-small-latest",
        temperature=0.0,
        max_tokens=300,  # Increased for more detailed contextual analysis
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

    # Cascade subcategory refinement
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
