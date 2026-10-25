"""Ties collection (Ruth's agent), Claude scoring and the math together, with the 24h SQLite cache.

Consumer: get_spots() and spot_detail(). Business: onboard(), score_business() (runs in the background),
insights() and rivals(). Demo data (backend/demo/) is handled in demo.py and never reaches this module's
live path.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import anthropic

import alerts
import collect
import config
import cuisines
import demo
import geo
import reviewer
import scoring
import store

LIVE_KEYS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY")
STALE_OK_HOURS = 24 * 30  # a month-old result beats an error when live collection fails

_area_locks: dict[str, threading.Lock] = {}
_area_locks_guard = threading.Lock()


class NotConfigured(RuntimeError):
    pass


class CollectionFailed(RuntimeError):
    pass


def require_live_keys() -> None:
    missing = [k for k in LIVE_KEYS if not config.has_key(k)]
    if missing:
        raise NotConfigured(f"Live scoring needs {' and '.join(missing)} in backend/.env. Use ?demo=true for sample data.")


def area_key(cuisine: str, lat: float, lng: float, radius_mi: float) -> str:
    return f"{cuisine}:{lat:.3f}:{lng:.3f}:{radius_mi:.2f}"


def maps_url(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}&travelmode=walking"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- one spot ----------

def score_reviews(name: str, cuisine: str, reviews: list[dict], client: anthropic.Anthropic | None = None) -> dict:
    """Claude's attribute scores plus wait and ambiance computed in code from the same review texts."""
    result = reviewer.score_spot(name, cuisine, reviews, client)
    used = result["reviewsUsed"]
    pct, rate = scoring.ambiance_stats(result["ambianceLabels"])
    return {
        "scores": result["scores"], "highlights": result["highlights"], "summary": result["summary"],
        "waitMinutes": scoring.wait_minutes([r["text"] for r in used]),
        "ambiancePct": pct, "ambianceMentionRate": rate, "reviewCount": len(used),
        "sourceKinds": sorted({r.get("source_kind", "search_snippet") for r in used}), "model": config.SCORING_MODEL,
    }


def unscored(cuisine: str) -> dict:
    return {"scores": {a["id"]: None for a in cuisines.scored_attributes(cuisine)}, "highlights": {}, "summary": "",
            "waitMinutes": None, "ambiancePct": None, "ambianceMentionRate": None, "reviewCount": 0, "sourceKinds": []}


def spot_view(spot: dict, metrics: dict) -> dict:
    """The /api/spots shape for one spot (bestAt, reason and pick are filled in by assemble)."""
    address = spot.get("address")
    return {
        "id": spot["id"], "name": spot["name"], "lat": spot["lat"], "lng": spot["lng"],
        "address": address, "street": (address or "").split(",")[0] or None,
        "price": spot.get("price"), "distanceMi": spot.get("distanceMi"),
        "scores": metrics["scores"], "waitMinutes": metrics["waitMinutes"],
        "ambiancePct": metrics["ambiancePct"], "ambianceMentionRate": metrics["ambianceMentionRate"],
        "bestAt": None, "reason": None, "reviewCount": metrics["reviewCount"],
        "sourceKinds": metrics["sourceKinds"], "collectionStatus": spot.get("collection_status", "complete"),
        "rating": spot.get("rating"), "platformReviewCount": spot.get("review_count") or spot.get("platform_review_count"),
        "pick": False,
        # Kept for bestAt/reason; dropped from the public list by assemble().
        "_highlights": metrics.get("highlights") or {}, "_summary": metrics.get("summary") or "",
    }


def assemble(cuisine: str, spots: list[dict], *, source: str, scraped_at: str, caveats: list[str]) -> dict:
    attrs = cuisines.compare_attributes(cuisine)
    by_id = {a["id"]: a for a in attrs}
    leads = scoring.best_at(spots, attrs)
    for s in spots:
        lead = leads.get(s["id"])
        s["bestAt"] = scoring.best_at_label(by_id[lead]) if lead else None
        s["reason"] = s["_highlights"].get(lead) or s["_summary"] or None
    top = scoring.pick(spots)
    pick_reason = None
    if top:
        top["pick"] = True
        avg = round(scoring.ranking_average(top))
        wait = f", about a {top['waitMinutes']}-min wait" if top["waitMinutes"] is not None else ""
        pick_reason = f"Highest average review score nearby ({avg}/100{wait}). {top['reason'] or ''}".strip()
    public = [{k: v for k, v in s.items() if not k.startswith("_")} for s in spots]
    statuses = {s["collectionStatus"] for s in public}
    return {
        "cuisine": cuisine, "spots": public, "pickId": top["id"] if top else None, "pickReason": pick_reason,
        "areaAverages": scoring.area_averages(spots, attrs),
        "reviewsRead": sum(s["reviewCount"] for s in public), "scrapedAt": scraped_at, "source": source,
        "collectionStatus": "complete" if statuses <= {"complete"} and public else "partial", "caveats": caveats,
    }


# ---------- consumer ----------

def _lock_for(key: str) -> threading.Lock:
    with _area_locks_guard:
        return _area_locks.setdefault(key, threading.Lock())


def get_spots(cuisine: str, lat: float, lng: float, radius_mi: float, *, depth: str = "fast", refresh: bool = False) -> dict:
    key = area_key(cuisine, lat, lng, radius_mi)
    if not refresh and (cached := store.get_area(key)):
        return {**cached["payload"], "source": "cache"}
    stale = store.get_area(key, max_age_hours=STALE_OK_HOURS)
    try:
        require_live_keys()
    except NotConfigured:
        if stale:
            return {**stale["payload"], "source": "cache", "stale": True}
        raise
    with _lock_for(key):  # one live run per area; a second caller waits and then reads the cache
        if not refresh and (cached := store.get_area(key)):
            return {**cached["payload"], "source": "cache"}
        try:
            payload = _score_area(cuisine, lat, lng, radius_mi, depth)
        except Exception as e:
            if stale:
                return {**stale["payload"], "source": "cache", "stale": True,
                        "caveats": [*stale["payload"].get("caveats", []), f"Live refresh failed: {e}"]}
            raise CollectionFailed(f"Couldn't collect {cuisine} spots right now ({e}).") from e
    return payload


def _score_area(cuisine: str, lat: float, lng: float, radius_mi: float, depth: str) -> dict:
    key = area_key(cuisine, lat, lng, radius_mi)
    previous = store.get_area(key, max_age_hours=STALE_OK_HOURS)  # to spot new #1s (top_rated alerts)
    collected = collect.collect(cuisine, lat, lng, radius_mi, depth)
    store.save_snapshot(collected["raw"], area_key=key)
    client = anthropic.Anthropic()

    def one(spot: dict) -> dict:
        try:
            metrics = score_reviews(spot["name"], cuisine, spot["reviews"], client)
        except reviewer.ScoringError as e:
            collect._log(f"{spot['name']}: scoring failed ({e})")
            metrics, spot["collection_status"] = unscored(cuisine), "partial"
        store.upsert_spot({**spot, "platform_review_count": spot.get("review_count")})
        store.save_score(spot["id"], cuisine, metrics)
        return spot_view(spot, metrics)

    with ThreadPoolExecutor(max_workers=4) as pool:
        views = list(pool.map(one, collected["spots"]))
    caveats = list(collected["caveats"])
    if not views:
        caveats.append("No spots with usable addresses were found nearby.")
    payload = assemble(cuisine, views, source="live", scraped_at=now_iso(), caveats=caveats)
    for alert in alerts.top_rated_alerts(cuisine, key, previous["payload"]["spots"] if previous else None, views):
        store.add_alert(alert)
    store.put_area(key, cuisine=cuisine, lat=lat, lng=lng, radius_mi=radius_mi, payload=payload, status=payload["collectionStatus"])
    return payload


def spot_detail(spot_id: str, cuisine: str | None = None) -> dict | None:
    spot = store.get_spot(spot_id)
    if not spot:
        return None
    scores = store.get_scores(spot_id)
    score = next((s for s in scores if s["cuisine"] == cuisine), None) if cuisine else (scores[0] if scores else None)
    details = spot.get("details") or {}
    return {
        "id": spot["id"], "name": spot["name"], "lat": spot["lat"], "lng": spot["lng"], "address": spot["address"],
        "price": spot["price"], "website": spot["website"], "rating": spot["rating"],
        "platformReviewCount": spot["platform_review_count"], "hours": spot["hours"],
        "cuisine": score["cuisine"] if score else None,
        "scores": score["scores"] if score else None, "highlights": score["highlights"] if score else {},
        "summary": score["summary"] if score else None,
        "waitMinutes": score["wait_minutes"] if score else None,
        "ambiancePct": score["ambiance_pct"] if score else None,
        "ambianceMentionRate": score["ambiance_mention_rate"] if score else None,
        "reviewCount": score["review_count"] if score else 0,
        "sourceKinds": score["source_kinds"] if score else [], "scoredAt": score["scored_at"] if score else None,
        "collectionStatus": spot["collection_status"],
        "praisedFor": details.get("praised_for", []), "complaints": details.get("complaints", []),
        "specialties": details.get("specialties", []), "pricePoints": details.get("price_points", []),
        "sources": details.get("sources", []),
        "reviews": [{"text": r["text"], "sourceKind": r.get("source_kind"), "sourceUrl": r.get("source_url"),
                     "publishedAt": r.get("published_at")} for r in spot.get("reviews", [])],
        "mapsUrl": maps_url(spot["lat"], spot["lng"]) if spot["lat"] is not None else None,
    }


# ---------- business ----------

def onboard(*, cuisine: str, name: str | None, address: str | None, place_id: str | None,
            lat: float | None, lng: float | None, goals: list[str], questionnaire: dict) -> str:
    details = geo.place_details(place_id) if place_id else None
    name = (details or {}).get("name") or name
    address = (details or {}).get("address") or address
    lat = (details or {}).get("lat") or lat
    lng = (details or {}).get("lng") or lng
    if not name:
        raise ValueError("Tell us the business name, or pick it from search.")
    if (lat is None or lng is None) and address:
        point = geo.geocode(address)
        lat, lng = point if point else (lat, lng)
    location = questionnaire.get("location") or (geo.area_label(lat, lng) if lat is not None else config.CAPITOL_HILL["label"])
    business_id = store.create_business(
        name=name, business_type=cuisine, location=location, address=address, lat=lat, lng=lng,
        place_id=place_id, website=(details or {}).get("website"), profile=questionnaire,
    )
    store.set_goals(business_id, goals)
    return business_id


def _area_for(business: dict) -> tuple[float, float]:
    if business["lat"] is not None and business["lng"] is not None:
        return business["lat"], business["lng"]
    return config.CAPITOL_HILL["lat"], config.CAPITOL_HILL["lng"]


def score_business(business_id: str, deep: bool = False) -> None:
    """Background job: score the area and this business from reviews, then link them. Never raises."""
    b = store.get_business(business_id)
    if not b:
        return
    store.update_business(business_id, scoring_status="running", scoring_error=None)
    try:
        cuisine = b["business_type"]
        lat, lng = _area_for(b)
        area = get_spots(cuisine, lat, lng, 1.0)
        store.upsert_competitors(business_id, [
            {"name": s["name"], "address": s["address"], "rating": s.get("rating"), "review_count": s.get("platformReviewCount"),
             "scores": s["scores"], "spot_id": s["id"]} for s in area["spots"]])

        # If discovery already found this business, use that spot so consumer picks count for it.
        match = next((s for s in area["spots"] if collect.slug(s["name"]) == collect.slug(b["name"])), None)
        status = "complete"
        if match:
            store.update_business(business_id, spot_id=match["id"])
        else:
            reviews, failures = collect.review_snippets(b["name"], b["address"], cuisine)
            try:
                metrics = score_reviews(b["name"], cuisine, reviews)
            except reviewer.ScoringError:
                metrics, failures = unscored(cuisine), [*failures, "scoring"]
            status = "partial" if failures else "complete"
            store.upsert_spot({"id": b["spot_id"], "name": b["name"], "address": b["address"], "lat": lat, "lng": lng,
                               "reviews": reviews, "collection_status": status})
            store.save_score(b["spot_id"], cuisine, metrics)

        if deep:  # Ruth's full research, for market_intelligence.product_gaps ("gap" in insights)
            from agent import competitor_agent as ruth
            report = ruth.research(b["name"], cuisines.research_type(b), b["address"] or b["location"], save=False, use_history=False)
            store.save_snapshot(report, business_id=business_id)
        store.update_business(business_id, scoring_status=status)
    except Exception as e:  # background job: record a plain-English reason instead of crashing
        store.update_business(business_id, scoring_status="failed", scoring_error=str(e)[:300])


def _business_context(b: dict) -> tuple[dict | None, list[dict]]:
    """(this business as a spot, the nearby spots) for insights and rivals."""
    cuisine = b["business_type"]
    if b["demo"]:
        return demo.business_you(), demo.spots(cuisine)["spots"]
    lat, lng = _area_for(b)
    cached = store.get_area(area_key(cuisine, lat, lng, 1.0), max_age_hours=STALE_OK_HOURS)
    area = cached["payload"]["spots"] if cached else []
    you = next((s for s in area if s["id"] == b["spot_id"]), None)
    if you is None:
        score = store.get_score(b["spot_id"], cuisine)
        if score:
            you = {"id": b["spot_id"], "name": b["name"], "scores": score["scores"], "waitMinutes": score["wait_minutes"],
                   "ambiancePct": score["ambiance_pct"], "ambianceMentionRate": score["ambiance_mention_rate"],
                   "reviewCount": score["review_count"]}
    return you, [s for s in area if s["id"] != b["spot_id"]]


def _gap(business_id: str) -> dict | None:
    snapshot = store.latest_snapshot(business_id)
    gaps = ((snapshot or {}).get("data") or {}).get("market_intelligence", {}).get("product_gaps") or []
    if not gaps:
        return None
    g = gaps[0]
    menu = "not on your menu" if g["owner_menu_status"] == "confirmed_absent" else "check whether you offer it"
    return {"text": f"{g['product']}: offered by {g['competitor_count']} nearby spots, with {g['positive_reviews']} positive "
                    f"and {g['request_reviews']} request mentions in reviews ({menu}; {g['confidence']} confidence).",
            "product": g["product"], "confidence": g["confidence"], "sourceUrls": g.get("source_urls", [])[:5]}


def _picks(b: dict, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return store.picks_since(b["business_type"], since, include_demo=bool(b["demo"]))


def insights(business_id: str) -> dict | None:
    b = store.get_business(business_id)
    if not b:
        return None
    base = {"businessId": business_id, "name": b["name"], "cuisine": b["business_type"], "status": b["scoring_status"],
            "error": b["scoring_error"], "demo": bool(b["demo"]), "period": "last 7 days"}
    if not cuisines.get(b["business_type"]):  # e.g. a bakery: crumbs only scores its own food types
        return {**base, "status": "unsupported", "reputation": None, "momentum": None, "edge": None, "breakdown": [],
                "wait": None, "ambiance": None, "biggestDrag": None, "gap": _gap(business_id)}
    you, area = _business_context(b)
    if you is None:
        return {**base, "reputation": None, "momentum": None, "edge": None, "breakdown": [], "wait": None,
                "ambiance": None, "biggestDrag": None, "gap": None}
    attrs = cuisines.compare_attributes(b["business_type"])
    rivals_info = scoring.rivals_report(you, _picks(b, 7), {s["id"]: s for s in [*area, you]}, attrs)
    result = scoring.insights(you, area, attrs, store.get_goals(business_id), rivals_info["picksWon"], rivals_info["picksLost"])
    return {**base, **result, "gap": _gap(business_id)}


def rivals(business_id: str, days: int) -> dict | None:
    b = store.get_business(business_id)
    if not b:
        return None
    if not cuisines.get(b["business_type"]):
        return {"businessId": business_id, "days": days, "demo": bool(b["demo"]), "status": "unsupported",
                "picksWon": 0, "picksLost": 0, "rivals": [], "whereYouWin": []}
    you, area = _business_context(b)
    base = {"businessId": business_id, "days": days, "demo": bool(b["demo"]), "status": b["scoring_status"]}
    if you is None:
        return {**base, "picksWon": 0, "picksLost": 0, "rivals": [], "whereYouWin": []}
    attrs = cuisines.compare_attributes(b["business_type"])
    return {**base, **scoring.rivals_report(you, _picks(b, days), {s["id"]: s for s in [*area, you]}, attrs)}
