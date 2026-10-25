"""Locations: distances, geocoding and place search.

Geocoding uses the free US Census geocoder, then OpenStreetMap Nominatim through Ruth's rate-limited,
disk-cached helper. Every address is looked up once and kept in SQLite. Place search uses Google
Places Autocomplete when GOOGLE_PLACES_API_KEY is set, otherwise Nominatim, biased to Capitol Hill.
"""

import functools
import math
import os
import time

import httpx

import config
import store
from agent import competitor_agent as ruth

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
PLACES_URL = "https://places.googleapis.com/v1"


def miles_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


@functools.lru_cache(maxsize=512)
def _neighborhood(lat: float, lng: float) -> str | None:
    """"Fremont, Seattle" for a point, from OpenStreetMap's reverse geocoder (1 request/second, like Ruth's helper)."""
    try:
        with ruth._nominatim_lock:
            wait = 1.0 - (time.monotonic() - ruth._nominatim_last[0])
            if wait > 0:
                time.sleep(wait)
            try:
                resp = httpx.get(NOMINATIM_REVERSE_URL, params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 14,
                                                                "addressdetails": 1}, headers=ruth.OSM_HEADERS, timeout=10)
            finally:
                ruth._nominatim_last[0] = time.monotonic()
        resp.raise_for_status()
        address = resp.json().get("address") or {}
    except (httpx.HTTPError, ValueError):
        return None
    area = address.get("neighbourhood") or address.get("suburb") or address.get("quarter")
    city = address.get("city") or address.get("town") or address.get("village")
    return f"{area}, {city}" if area and city else city


def area_label(lat: float, lng: float) -> str:
    """The place name Ruth's agent searches around: the demo area by name, else the point's neighborhood
    ("Fremont, Seattle"), else Seattle."""
    hill = config.CAPITOL_HILL
    if miles_between(lat, lng, hill["lat"], hill["lng"]) <= 1.5:
        return hill["label"]
    return _neighborhood(round(lat, 4), round(lng, 4)) or "Seattle, WA"


def full_address(address: str, city: str = "Seattle, WA") -> str:
    """OSM gives "137 15th Ave E"; the geocoders need the city too."""
    return address if "," in address else f"{address}, {city}"


def geocode(address: str) -> tuple[float, float] | None:
    """(lat, lng) for an address, or None. Cached forever in SQLite, including misses."""
    if not address or not address.strip():
        return None
    query = full_address(address.strip())
    cached = store.get_geocode(query)
    if cached:
        return (cached["lat"], cached["lng"]) if cached["lat"] is not None else None

    point, source = None, "none"
    try:
        resp = httpx.get(CENSUS_URL, params={"address": query, "benchmark": "Public_AR_Current", "format": "json"}, timeout=15)
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if matches:
            point, source = (matches[0]["coordinates"]["y"], matches[0]["coordinates"]["x"]), "census"
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    if point is None:
        try:
            found = ruth._nominatim({"q": query, "limit": 1})
            if found:
                point, source = (float(found[0]["lat"]), float(found[0]["lon"])), "nominatim"
        except (httpx.HTTPError, ValueError):
            pass
    store.put_geocode(query, point[0] if point else None, point[1] if point else None, source)
    return point


# ---------- place search for business onboarding ----------

def _google(method: str, path: str, field_mask: str, body: dict | None = None) -> dict:
    resp = httpx.request(
        method, f"{PLACES_URL}/{path}", json=body, timeout=15,
        headers={"X-Goog-Api-Key": os.environ["GOOGLE_PLACES_API_KEY"], "X-Goog-FieldMask": field_mask},
    )
    resp.raise_for_status()
    return resp.json()


def search_places(q: str, limit: int = 8) -> list[dict]:
    """[{placeId, name, address, lat, lng, source}] for a business-name search near Capitol Hill."""
    hill = config.CAPITOL_HILL
    if config.has_key("GOOGLE_PLACES_API_KEY"):
        data = _google("POST", "places:autocomplete", "suggestions.placePrediction.placeId,suggestions.placePrediction.structuredFormat", {
            "input": q,
            "locationBias": {"circle": {"center": {"latitude": hill["lat"], "longitude": hill["lng"]}, "radius": 3000.0}},
        })
        results = []
        for s in data.get("suggestions", [])[:limit]:
            p = s.get("placePrediction") or {}
            fmt = p.get("structuredFormat") or {}
            results.append({
                "placeId": p.get("placeId"),
                "name": (fmt.get("mainText") or {}).get("text"),
                "address": (fmt.get("secondaryText") or {}).get("text"),
                "lat": None, "lng": None,  # filled in by place_details on onboarding
                "source": "google",
            })
        return [r for r in results if r["placeId"] and r["name"]]

    # Nominatim: bias (not restrict) to a box around Capitol Hill.
    d = 0.05
    found = ruth._nominatim({"q": q, "limit": limit, "addressdetails": 1, "bounded": 0,
                             "viewbox": f"{hill['lng'] - d},{hill['lat'] + d},{hill['lng'] + d},{hill['lat'] - d}"})
    results = []
    for el in found:
        addr = el.get("address") or {}
        street = " ".join(filter(None, [addr.get("house_number"), addr.get("road")]))
        city = addr.get("city") or addr.get("town") or ""
        results.append({
            "placeId": f"osm:{el.get('osm_type')}/{el.get('osm_id')}",
            "name": el.get("name") or (el.get("display_name") or "").split(",")[0],
            "address": ", ".join(filter(None, [street, city])) or el.get("display_name"),
            "lat": float(el["lat"]), "lng": float(el["lon"]),
            "source": "osm",
        })
    return results


def place_details(place_id: str) -> dict | None:
    """{name, address, lat, lng, website, rating, reviewCount} for a placeId from search_places."""
    # OSM search results already carry name, address and coordinates, so onboarding sends those along
    # with an "osm:" id instead of looking it up again.
    if place_id.startswith("osm:") or not config.has_key("GOOGLE_PLACES_API_KEY"):
        return None
    p = _google("GET", f"places/{place_id}", "id,displayName,formattedAddress,location,websiteUri,rating,userRatingCount")
    loc = p.get("location") or {}
    return {
        "name": (p.get("displayName") or {}).get("text"),
        "address": p.get("formattedAddress"),
        "lat": loc.get("latitude"), "lng": loc.get("longitude"),
        "website": p.get("websiteUri"),
        "rating": p.get("rating"), "reviewCount": p.get("userRatingCount"),
    }
