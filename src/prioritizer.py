"""News prioritization logic with category-based weights and personalization."""

from typing import Any, Dict

from src.user_profile import UserProfile

# Base weights for categories (relative importance)
CATEGORY_WEIGHTS = {
    "economy_finance": 1.2,
    "politics_geopolitics": 1.2,
    "technology_ai_science": 1.1,
    "real_estate_housing": 1.0,
    "career_education_labour": 1.0,
    "sports": 1.0,  # neutral baseline
    "energy_climate_environment": 1.0,
    "culture_media_entertainment": 0.9,
    "healthcare_pharma": 1.0,
    "transport_auto_aviation": 0.9,
}


def adjust_priority(classification: Dict[str, Any], user: UserProfile) -> int:
    """Adjust priority score based on category and user interests."""

    base_priority = classification.get("priority_llm", 5)
    category = classification.get("category", "other")
    subcategory = classification.get("sports_subcategory")

    # Step 1: Apply category weight
    weight = CATEGORY_WEIGHTS.get(category, 1.0)
    adjusted = base_priority * weight

    # Step 2: Boost if category or subcategory is in user interests
    if category in user.interests or (subcategory and subcategory in user.interests):
        adjusted *= 1.1  # soft boost (10% increase)

    # Step 3: Clamp into [1, 10]
    adjusted = max(1, min(10, round(adjusted)))

    return adjusted
