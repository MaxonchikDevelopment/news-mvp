"""User profile management for personalization (MVP version)."""

from typing import Dict, List, Optional


class UserProfile:
    """Represents a user profile with personalization settings."""

    def __init__(
        self,
        user_id: str,
        interests: List[str],
        locale: Optional[str] = None,
        city: Optional[str] = None,
        language: str = "en",
    ):
        """
        Args:
            user_id (str): Unique identifier of the user.
            interests (List[str]): List of categories user is interested in.
            locale (Optional[str]): Country/region code (e.g., "US", "DE").
            city (Optional[str]): Specific city/region (e.g., "New York").
            language (str): Preferred language for output (default: "en").
        """
        self.user_id = user_id
        self.interests = interests
        self.locale = locale
        self.city = city
        self.language = language


# Hardcoded test profile (later replace with DB storage)
USER_PROFILES: Dict[str, UserProfile] = {
    "test_user": UserProfile(
        user_id="test_user",
        interests=["economy_finance", "technology_ai_science", "sports"],
        locale="US",
        city="New York",
        language="en",
    )
}


def get_user_profile(user_id: str) -> Optional[UserProfile]:
    """Fetch a user profile by ID.

    Args:
        user_id (str): The unique ID of the user.

    Returns:
        UserProfile | None: Profile object with preferences, or None if not found.
    """
    return USER_PROFILES.get(user_id)
