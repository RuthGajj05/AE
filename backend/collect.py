"""Find spots for a food type and area and collect their review text, using Ruth's agent (agent/).

fast (default): fast_competitors' discovery (OpenStreetMap + one web search) and competitor pick, then
  per spot, in parallel: fast_competitors' one-competitor agent for listing facts, plus Ruth's
  search_web for review snippets (source_kind "search_snippet") and, with a Google key, her Places
  review sample ("google_places_sample").
deep: competitor_agent.research (multi-source specialists); its evidence_bundle.review_observations
  are the review texts, with Ruth's source_kind labels unchanged.

Fast mode's one-competitor agents only return short summary phrases, so review text always comes from
the raw search results or Places reviews, never from those summaries. A source that fails marks the
spot "partial" instead of failing the area.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import geo
from agent import competitor_agent as ruth
from agent import fast_competitors as fast

# How OpenStreetMap and web search name each food type.
PLACE_TYPES = {
    "sushi": ["sushi", "japanese restaurant"],
    "ramen": ["ramen", "noodle shop"],
    "steak": ["steakhouse", "steak"],
    "pizza": ["pizza", "pizzeria"],
    "tacos": ["taqueria", "mexican restaurant", "tacos"],
}
REVIEW_SNIPPETS = 8


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def spot_id(name: str, address: str | None) -> str:
    number = re.match(r"\s*(\d+)", address or "")
    return f"spot-{slug(name)}" + (f"-{number.group(1)}" if number else "")


def _log(message: str) -> None:
    print(f"[crumbs] {message}", file=sys.stderr)


def _json(text: str):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None  # Ruth's tools return plain-English strings for "no results" and failures


def review_snippets(name: str, address: str | None, cuisine: str) -> tuple[list[dict], list[str]]:
    """Review texts for one spot from web search and (if configured) Google Places. Returns (reviews, failures)."""
    reviews: list[dict] = []
    failures: list[str] = []
    query = f"{name} {address or ''} {cuisine} reviews".replace("  ", " ")
    found = _json(ruth.search_web.call({"query": query, "purpose": "reviews", "max_results": REVIEW_SNIPPETS}))
    if isinstance(found, list):
        for r in found:
            if r.get("snippet"):
                reviews.append({"text": r["snippet"], "source_kind": r.get("source_kind", "search_snippet"),
                                "source_url": r.get("url"), "published_at": None})
    else:
        failures.append("web reviews")

    if ruth.GOOGLE_PLACES_API_KEY:
        places = _json(ruth.find_places.call({"query": f"{name} {address or ''}", "max_results": 1}))
        place = places[0] if isinstance(places, list) and places else None
        detail = _json(ruth.get_place_reviews.call({"place_id": place["id"]})) if place else None
        if isinstance(detail, dict):
            for r in detail.get("reviews", []):
                if r.get("text"):
                    # Reviewer names (author_attribution) are deliberately not kept.
                    reviews.append({"text": r["text"], "source_kind": "google_places_sample",
                                    "source_url": r.get("source_url"), "published_at": r.get("published_at")})
        else:
            failures.append("Google reviews")
    return reviews, failures


def _fast_one(pick: fast.Pick, cuisine: str, label: str) -> dict:
    facts, failures = {}, []
    try:
        facts = fast._research_one(pick, f"{cuisine} restaurant", label, []) or {}
    except Exception as e:  # one bad spot must not sink the area
        _log(f"{pick.name}: listing facts failed ({e})")
        failures.append("listing facts")
    address = facts.get("address") or pick.address
    reviews, review_failures = review_snippets(pick.name, address, cuisine)
    return {"name": facts.get("name") or pick.name, "address": address, "website": facts.get("website") or pick.website,
            "rating": facts.get("rating"), "review_count": facts.get("review_count"), "hours": facts.get("hours"),
            "details": {k: facts.get(k) or [] for k in ("price_points", "praised_for", "complaints", "specialties", "sources")},
            "reviews": reviews, "failures": failures + review_failures}


def collect_fast(cuisine: str, label: str, radius_mi: float) -> dict:
    osm = ruth.find_nearby_osm.call({"location": label, "place_types": PLACE_TYPES[cuisine], "radius_m": int(radius_mi * 1609)})
    web = ruth.search_web.call({"query": f"best {cuisine} in {label}", "purpose": "discovery"})
    picks = fast._pick(f"(none: a diner comparing {cuisine} spots)", f"{cuisine} restaurant", label, osm, web)
    _log(f"{cuisine}: picked {len(picks)} spots near {label}")
    with ThreadPoolExecutor(max_workers=max(1, len(picks))) as pool:
        spots = list(pool.map(lambda p: _fast_one(p, cuisine, label), picks))
    return {"collector": "fast", "spots": spots, "caveats": [], "raw": {"osm": _json(osm), "picks": [p.model_dump() for p in picks]}}


def collect_deep(cuisine: str, label: str) -> dict:
    report = ruth.research(f"(none: a diner comparing {cuisine} spots)", f"{cuisine} restaurant", label,
                           save=False, use_history=False)
    observations = (report.get("evidence_bundle") or {}).get("review_observations", [])
    spots = []
    for c in report.get("competitors", []):
        own = [o for o in observations if slug(o.get("business_name", "")) == slug(c["name"])]
        spots.append({
            "name": c["name"], "address": c.get("address"), "website": c.get("website"), "rating": c.get("rating"),
            "review_count": c.get("review_count"), "hours": c.get("hours"),
            "details": {k: c.get(k) or [] for k in ("price_points", "praised_for", "complaints", "specialties", "sources")},
            "reviews": [{"text": o["text"], "source_kind": o.get("source_kind", "search_snippet"),
                         "source_url": o.get("source_url"), "published_at": o.get("published_at")} for o in own],
            "failures": [] if report.get("collection_status", "complete") == "complete" else ["some sources"],
        })
    return {"collector": "deep", "spots": spots, "caveats": report.get("gaps_and_caveats", []), "raw": report}


def collect(cuisine: str, lat: float, lng: float, radius_mi: float, depth: str = "fast") -> dict:
    """Spots near (lat, lng) with review texts and coordinates. Spots that can't be placed on a map are dropped."""
    label = geo.area_label(lat, lng)
    result = collect_deep(cuisine, label) if depth == "deep" else collect_fast(cuisine, label, radius_mi)
    placed, dropped = [], []
    for s in result["spots"]:
        point = geo.geocode(s["address"]) if s.get("address") else None
        if point is None:
            dropped.append(s["name"])
            continue
        s["lat"], s["lng"] = point
        s["distanceMi"] = round(geo.miles_between(lat, lng, *point), 2)
        if s["distanceMi"] > radius_mi * 1.25:  # discovery can reach a little past the circle; not far past it
            dropped.append(s["name"])
            continue
        s["id"] = spot_id(s["name"], s["address"])
        s["collection_status"] = "partial" if s["failures"] else "complete"
        placed.append(s)
    if dropped:
        result["caveats"].append(f"Left out (no usable address or outside {radius_mi} mi): {', '.join(dropped)}")
    result["spots"] = sorted(placed, key=lambda s: s["distanceMi"])
    result["label"] = label
    return result
