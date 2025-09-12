# src/user_profile.py
"""User profile management for personalization (MVP version).

Provides:
- UserProfile class for storing personalization preferences.
- Robust location normalization via GeoNames (through src.locations.find_city)
  and pycountry (through src.locations.normalize_country).
- Simple in-memory profile store (USER_PROFILES).

Safe to import as a module or run as a script for quick manual tests.
"""

from typing import Dict, List, Optional, Union

from src.locations import find_city, normalize_country


class UserProfile:
    """Represents a user profile with personalization settings.

    Attributes:
        user_id: Unique identifier for the user.
        interests: List of category strings or dicts for subcategories.
        locale: Two-letter ISO country code (e.g., "DE", "US"), or None.
        city: Normalized city name, or None.
        language: Preferred output language (default: "en").
    """

    def __init__(
        self,
        user_id: str,
        interests: Optional[List[Union[str, dict]]] = None,
        locale: Optional[str] = None,
        city: Optional[str] = None,
        language: str = "en",
    ) -> None:
        self.user_id = user_id
        self.interests = interests or []
        self.locale: Optional[str] = None
        self.city: Optional[str] = None
        self.language = language

        # Normalize immediately if location data is provided
        if city or locale:
            self.set_location(city=city, country=locale)

    def set_location(
        self, city: Optional[str] = None, country: Optional[str] = None
    ) -> Optional[dict]:
        """Normalize and set location.

        Order of resolution:
        1) If city is provided, try GeoNames lookup -> sets both city and country.
        2) If city lookup fails but country is provided, normalize via pycountry.
        3) If both fail, keep locale and city as None.

        Args:
            city: Raw city name string.
            country: Raw country name or code string.

        Returns:
            A dict with {"city": ..., "countryCode": ...} if successful, else None.
        """
        # 1) Try resolving via GeoNames
        if city:
            city_data = find_city(city)
            if city_data:
                normalized_city = (
                    city_data.get("city")
                    or city_data.get("name")
                    or city_data.get("toponymName")
                    or city_data.get("asciiName")
                )
                self.city = normalized_city or city.strip()

                country_code = city_data.get("countryCode") or city_data.get(
                    "countrycode"
                )
                if country_code:
                    self.locale = country_code.upper()
                elif country:
                    self.locale = normalize_country(country)

                return {"city": self.city, "countryCode": self.locale}

        # 2) Fallback: normalize country only
        if country:
            normalized_country = normalize_country(country)
            if normalized_country:
                self.locale = normalized_country
                return {"city": None, "countryCode": self.locale}

        # 3) Nothing resolved
        return None

    def to_dict(self) -> Dict[str, Optional[Union[str, List[Union[str, dict]]]]]:
        """Return a simple serializable representation of the profile."""
        return {
            "user_id": self.user_id,
            "interests": self.interests,
            "locale": self.locale,
            "city": self.city,
            "language": self.language,
        }

    def __repr__(self) -> str:
        return (
            f"<UserProfile {self.user_id}: "
            f"locale={self.locale}, city={self.city}, "
            f"interests={self.interests}, lang={self.language}>"
        )


# Temporary in-memory store (later replaced with DB persistence)
USER_PROFILES: Dict[str, UserProfile] = {
    "Maxonchik": UserProfile(
        user_id="Maxonchik",
        interests=[
            "economy_finance",
            "technology_ai_science",
            {"sports": ["basketball_nba", "football_epl", "formula1"]},
        ],
        locale="Germany",  # Free-form string -> normalized to "DE"
        city="Frankfurt",  # GeoNames resolves to "Frankfurt am Main"
        language="en",
    )
}


def get_user_profile(user_id: str) -> Optional[UserProfile]:
    """Fetch a user profile by its ID."""
    return USER_PROFILES.get(user_id)
