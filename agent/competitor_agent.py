"""Competitor research agent.

Given a business (name, type, location), Claude uses OpenStreetMap to find
nearby competitors, Tavily to find their ratings, reviews and prices, and
submits a structured report. Google Places is used too if a key is set.

Usage:
    python agent/competitor_agent.py "Sweet Crumb Bakery" bakery "Capitol Hill, Seattle"
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path

import anthropic
import httpx
from anthropic import beta_tool
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from tavily import TavilyClient

from sources import BLOCKED_DOMAINS, DISCOVERY_DOMAINS, REVIEW_DOMAINS

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "claude-opus-5-5"
MAX_PAGE_CHARS = 6000  # per extracted page, to keep tool results a sane size
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
PLACES_URL = "https://places.googleapis.com/v1"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# OpenStreetMap's usage policy requires an identifying User-Agent.
OSM_HEADERS = {"User-Agent": "AE-competitor-research/0.1 (student project)"}


# ---------- Report schema ----------

class Competitor(BaseModel):
    name: str
    address: str | None = None
    distance_note: str | None = Field(None, description="e.g. '0.3 mi, same street'")
    website: str | None = None
    rating: float | None = Field(None, description="Average star rating, if found")
    review_count: int | None = None
    specialties: list[str] = Field(default_factory=list)
    price_points: list[str] = Field(
        default_factory=list, description="Item and price, e.g. 'Croissant: $4.75'"
    )
    praised_for: list[str] = Field(default_factory=list, description="Recurring positives in reviews")
    complaints: list[str] = Field(default_factory=list, description="Recurring negatives in reviews")
    sources: list[str] = Field(default_factory=list, description="URLs this entry is based on")


class Insight(BaseModel):
    recommendation: str
    evidence: str = Field(description="The specific findings that support it, with counts where possible")


# ---------- Tools ----------

@beta_tool
def search_web(query: str, purpose: str = "general", max_results: int = 8) -> str:
    """Search the web with Tavily.

    Args:
        query: Search query, e.g. "bakeries near Capitol Hill Seattle".
        purpose: "discovery" to find nearby businesses, "reviews" to find customer reviews, or "general".
        max_results: Number of results to return (1-15).
    """
    domains = {"discovery": DISCOVERY_DOMAINS, "reviews": REVIEW_DOMAINS}.get(purpose, [])
    try:
        resp = tavily.search(
            query=query,
            search_depth="advanced",
            max_results=max(1, min(max_results, 15)),
            include_domains=domains or None,
            exclude_domains=BLOCKED_DOMAINS or None,
        )
    except Exception as e:
        return f"Search failed: {e}"
    results = [
        {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")}
        for r in resp.get("results", [])
    ]
    return json.dumps(results) if results else "No results."


@beta_tool
def read_pages(urls: list[str]) -> str:
    """Extract the text of up to 5 web pages (menus, review pages, listings).

    Args:
        urls: Page URLs taken from search results.
    """
    urls = [u for u in urls if not any(d in u for d in BLOCKED_DOMAINS)][:5]
    if not urls:
        return "No allowed URLs given."
    try:
        resp = tavily.extract(urls=urls, extract_depth="advanced", format="markdown")
    except Exception as e:
        return f"Extract failed: {e}"
    pages = []
    for r in resp.get("results", []):
        text = r.get("raw_content") or ""
        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS] + f"\n[truncated: page was {len(text)} chars]"
        pages.append({"url": r.get("url"), "content": text})
    for r in resp.get("failed_results", []):
        pages.append({"url": r.get("url"), "error": r.get("error", "could not extract")})
    return json.dumps(pages)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(6371000 * 2 * math.asin(math.sqrt(a)))


@beta_tool
def find_nearby_osm(location: str, osm_tags: list[str], radius_m: int = 1500) -> str:
    """Find businesses near a location using OpenStreetMap (free). Returns name, address, distance,
    opening hours, website, phone and dietary tags, sorted by distance. No ratings or reviews.

    Args:
        location: Neighborhood and city, e.g. "Capitol Hill, Seattle".
        osm_tags: OpenStreetMap key=value tags for the business type, e.g. ["shop=bakery", "shop=pastry"] for bakeries, ["shop=pet_grooming"] for dog groomers, ["amenity=cafe"] for cafes.
        radius_m: Search radius in meters (100-5000).
    """
    try:
        geo = httpx.get(
            NOMINATIM_URL, params={"q": location, "format": "json", "limit": 1},
            headers=OSM_HEADERS, timeout=30,
        )
        geo.raise_for_status()
        if not geo.json():
            return f"Could not find location: {location}"
        lat, lon = float(geo.json()[0]["lat"]), float(geo.json()[0]["lon"])

        radius_m = max(100, min(radius_m, 5000))
        filters = "".join(
            f'nwr["{k}"="{v}"](around:{radius_m},{lat},{lon});'
            for k, v in (t.split("=", 1) for t in osm_tags if "=" in t)
        )
        if not filters:
            return "No valid key=value tags given."
        # The public Overpass server is often briefly overloaded (429/504); retry a few times.
        for attempt in range(3):
            resp = httpx.post(
                OVERPASS_URL, data={"data": f"[out:json][timeout:25];({filters});out center tags;"},
                headers=OSM_HEADERS, timeout=60,
            )
            if resp.status_code not in (429, 502, 503, 504):
                break
            time.sleep(5 * (attempt + 1))
        resp.raise_for_status()
    except Exception as e:
        return f"OpenStreetMap lookup failed: {e}"

    places = []
    for el in resp.json().get("elements", []):
        tags = el.get("tags", {})
        if "name" not in tags:
            continue
        plat = el.get("lat") or el.get("center", {}).get("lat")
        plon = el.get("lon") or el.get("center", {}).get("lon")
        address = " ".join(
            tags[k] for k in ("addr:housenumber", "addr:street", "addr:unit") if k in tags
        )
        places.append({
            "name": tags["name"],
            "address": address or None,
            "distance_m": _distance_m(lat, lon, plat, plon) if plat and plon else None,
            "type": next((t for t in osm_tags if tags.get(t.split("=")[0]) == t.split("=", 1)[1]), None),
            "opening_hours": tags.get("opening_hours"),
            "website": tags.get("website") or tags.get("contact:website"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "diet": {k[5:]: v for k, v in tags.items() if k.startswith("diet:")} or None,
            "osm_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        })
    places.sort(key=lambda p: p["distance_m"] if p["distance_m"] is not None else 1e9)
    return json.dumps({"center": {"lat": lat, "lon": lon}, "places": places[:25]})


def _places_request(method: str, path: str, field_mask: str, body: dict | None = None) -> dict:
    if not GOOGLE_PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")
    resp = httpx.request(
        method,
        f"{PLACES_URL}/{path}",
        headers={"X-Goog-Api-Key": GOOGLE_PLACES_API_KEY, "X-Goog-FieldMask": field_mask},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


@beta_tool
def find_places(query: str, max_results: int = 15) -> str:
    """Find businesses on Google Maps, with per-location rating, review count, address, hours and website.

    Args:
        query: e.g. "bakery in Capitol Hill, Seattle".
        max_results: Number of places to return (1-20).
    """
    fields = ",".join(
        f"places.{f}"
        for f in [
            "id", "displayName", "formattedAddress", "businessStatus", "primaryType",
            "rating", "userRatingCount", "priceLevel", "priceRange", "websiteUri",
            "googleMapsUri", "regularOpeningHours.weekdayDescriptions",
        ]
    )
    try:
        data = _places_request(
            "POST", "places:searchText", fields,
            {"textQuery": query, "pageSize": max(1, min(max_results, 20))},
        )
    except Exception as e:
        return f"Google Places search failed: {e}"
    places = data.get("places", [])
    for p in places:
        p["displayName"] = p.get("displayName", {}).get("text")
    return json.dumps(places) if places else "No places found."


@beta_tool
def get_place_reviews(place_id: str) -> str:
    """Get up to 5 recent Google reviews (full text) for one place.

    Args:
        place_id: The "id" from a find_places result.
    """
    try:
        data = _places_request("GET", f"places/{place_id}", "id,displayName,rating,userRatingCount,reviews")
    except Exception as e:
        return f"Google Places details failed: {e}"
    reviews = [
        {
            "rating": r.get("rating"),
            "when": r.get("relativePublishTimeDescription"),
            "text": (r.get("text") or {}).get("text"),
        }
        for r in data.get("reviews", [])
    ]
    return json.dumps({
        "name": data.get("displayName", {}).get("text"),
        "rating": data.get("rating"),
        "review_count": data.get("userRatingCount"),
        "reviews": reviews,
    })


submitted: dict = {}


@beta_tool
def submit_report(
    market_summary: str,
    competitors: list[Competitor],
    price_benchmarks: list[str],
    insights: list[Insight],
    gaps_and_caveats: list[str],
) -> str:
    """Submit the final competitor report. Call this exactly once, when research is done.

    Args:
        market_summary: 3-5 sentences on the local competitive landscape.
        competitors: One entry per nearby competitor found.
        price_benchmarks: Typical price ranges for core items, e.g. "Sourdough loaf: $9-$13 (6 shops)".
        insights: 3-5 actionable recommendations for the owner, each backed by evidence.
        gaps_and_caveats: What couldn't be verified or found (missing prices, stale data, etc.).
    """
    submitted.update(
        market_summary=market_summary,
        competitors=[c.model_dump() for c in competitors],
        price_benchmarks=price_benchmarks,
        insights=[i.model_dump() for i in insights],
        gaps_and_caveats=gaps_and_caveats,
    )
    return "Report received."


SYSTEM = """You research the local competition for a small, brick-and-mortar business so its owner can stay competitive.

Work in this order:
1. Find businesses of the same type close to the given location with find_nearby_osm. OpenStreetMap is volunteer-maintained, so it can miss new shops or list closed ones: also run search_web with purpose="discovery" (e.g. "best bakeries in <location>") to find the well-known local competitors. Choose 8-10 direct competitors, balancing the closest ones with the most prominent ones: a shop with hundreds of reviews in the neighborhood matters even if it's a little farther away or missing from OpenStreetMap. Drop any that a recent source says have closed.
2. Get each competitor's rating, review count and what customers praise or complain about with search_web, purpose="reviews". Include the street address in the query (e.g. "Bakery Nouveau 137 15th Ave E Seattle reviews") so you get that branch, not another location of the same business. Yelp and TripAdvisor pages can't be read with read_pages, only their search snippets. If a rating clearly belongs to another branch or the snippet doesn't say, say so.
3. Find prices for core items on each business's own website with read_pages. If its site has no prices or won't load, don't stop there: search_web for "<name> <item> price" or "<name> menu prices", and try online ordering pages (Square, Toast, Clover), menu-listing sites, and recent articles or reviews that quote prices. Search snippets often contain prices even when the page itself can't be read. Prefer in-store prices; if you use a delivery-app price, say so. Aim for at least 3 shops' prices for each core item in price_benchmarks.
4. Call submit_report once with everything you found.

If find_places and get_place_reviews are available, prefer them for ratings and reviews: their data belongs to one exact location.

Rules:
- Only report facts you saw in a tool result, and list the URLs each competitor entry is based on. If a price or rating isn't found, leave it empty and mention it in gaps_and_caveats. Never estimate prices.
- Recommendations must be specific and cite evidence (e.g. "4 of 7 nearby bakeries have no gluten-free options; 12 reviews ask for them"), not generic advice.
- Search and read pages in parallel when the calls don't depend on each other."""


def run(business: str, business_type: str, location: str) -> dict:
    client = anthropic.Anthropic()
    submitted.clear()
    tools = [find_nearby_osm, search_web, read_pages, submit_report]
    if GOOGLE_PLACES_API_KEY:  # paid; only used when a key is configured
        tools[1:1] = [find_places, get_place_reviews]
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        max_iterations=40,
        system=SYSTEM,
        tools=tools,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": f"Business: {business}\nType: {business_type}\nLocation: {location}",
        }],
    )
    for message in runner:
        for block in message.content:
            if block.type == "tool_use":
                print(f"  -> {block.name}: {json.dumps(block.input)[:120]}", file=sys.stderr)
        if message.stop_reason == "refusal":
            raise RuntimeError(f"Request was declined: {message.stop_details}")

    if not submitted:
        raise RuntimeError("Agent finished without submitting a report.")
    return {
        "business": business,
        "type": business_type,
        "location": location,
        "date": date.today().isoformat(),
        **submitted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business", help="Business name")
    parser.add_argument("business_type", help="e.g. bakery, dog groomer, cafe")
    parser.add_argument("location", help="Neighborhood and city, e.g. 'Ballard, Seattle'")
    args = parser.parse_args()

    report = run(args.business, args.business_type, args.location)

    REPORTS_DIR.mkdir(exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in args.business.lower()).strip("-")
    out = REPORTS_DIR / f"{slug}-{report['date']}.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\n{report['market_summary']}\n\nSaved {len(report['competitors'])} competitors to {out}")


if __name__ == "__main__":
    main()
