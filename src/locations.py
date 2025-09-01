# src/locations.py
import os
from typing import Dict, Optional

import geonamescache
import pycountry
import requests
from dotenv import load_dotenv

# загрузка переменных окружения
load_dotenv()

GEONAMES_USERNAME = os.getenv("GEONAMES_USERNAME")

if not GEONAMES_USERNAME:
    raise RuntimeError(
        "GeoNames username not set. Please define GEONAMES_USERNAME in your .env file."
    )

gc = geonamescache.GeonamesCache()


def normalize_country(name_or_code: str) -> Optional[str]:
    """Return ISO2 country code (e.g. 'DE', 'US') or None."""
    if not name_or_code:
        return None
    name = name_or_code.strip()
    # try direct ISO
    if len(name) == 2 and name.isalpha():
        return name.upper()
    # try pycountry lookup
    try:
        c = pycountry.countries.lookup(name)
        return c.alpha_2
    except Exception:
        return None


def find_city(name: str, max_rows: int = 1) -> Optional[Dict]:
    """
    Search city using GeoNames API, fallback to local geonamescache.
    Returns normalized dict or None.

    Example:
        {
            "city": "Berlin",
            "country": "Germany",
            "countryCode": "DE",
            "lat": 52.52,
            "lng": 13.41,
            "population": 3426354
        }
    """
    if not name:
        return None

    url = "http://api.geonames.org/searchJSON"
    params = {
        "q": name,
        "maxRows": max_rows,
        "username": GEONAMES_USERNAME,
        "featureClass": "P",  # only populated places (cities, villages, towns)
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        geonames = data.get("geonames", [])
        if geonames:
            g = geonames[0]
            return {
                "city": g.get("name"),
                "country": g.get("countryName"),
                "countryCode": g.get("countryCode"),
                "lat": float(g.get("lat")),
                "lng": float(g.get("lng")),
                "population": int(g.get("population", 0)),
            }
    except Exception as e:
        print(f"GeoNames API error: {e}")

    # fallback на локальный словарь (без координат)
    try:
        lname = name.lower()
        for cid, info in gc.get_cities().items():
            if info["name"].lower() == lname:
                country_code = info.get("countrycode")
                country_name = None
                if country_code:
                    try:
                        c = pycountry.countries.get(alpha_2=country_code)
                        if c:
                            country_name = c.name
                    except Exception:
                        pass
                return {
                    "city": info["name"],
                    "country": country_name,
                    "countryCode": country_code,
                    "lat": None,
                    "lng": None,
                    "population": None,
                }
    except Exception:
        pass

    return None
