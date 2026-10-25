"""Demo mode: fixtures from backend/demo/ so the stage demo never depends on live scraping.

On with DEMO_MODE=1 or ?demo=true. Fixtures use the frontend's mock shapes and made-up spot names, and
every response is flagged demo: true. seed() adds the demo business (biz-tamago, a made-up sushi shop)
and ~30 demo picks for Capitol Hill sushi so the Rivals screen has data; demo picks are flagged in the
picks table and never count for real businesses.
"""

import copy
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import config
import store

BUSINESS_ID = "biz-tamago"


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    return json.loads((config.DEMO_DIR / name).read_text())


def spots(cuisine: str) -> dict:
    return copy.deepcopy(_load(f"spots-{cuisine}.json"))


def spot_detail(spot_id: str) -> dict | None:
    for path in sorted(config.DEMO_DIR.glob("spots-*.json")):
        payload = _load(path.name)
        for s in payload["spots"]:
            if s["id"] == spot_id:
                return {**copy.deepcopy(s), "cuisine": payload["cuisine"], "highlights": {}, "summary": s["reason"],
                        "reviews": [], "praisedFor": [], "complaints": [], "specialties": [], "pricePoints": [],
                        "sources": [], "demo": True,
                        "mapsUrl": f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lng']}&travelmode=walking"}
    return None


def places(q: str) -> list[dict]:
    q = q.lower().strip()
    return [p for p in _load("places.json")["results"] if q in p["name"].lower()][:8]


def alerts(*, audience: str, business_id: str | None, lat: float | None, lng: float | None, radius_mi: float,
           cuisine: str | None = None) -> list[dict]:
    """backend/demo/alerts.json in the live shape; "minutesAgo" becomes createdAt so the demo always looks recent."""
    import geo  # here, not at the top: geo imports Ruth's agent, which demo mode doesn't need

    now = datetime.now(timezone.utc)
    rows = [a for a in _load("alerts.json")["alerts"] if a["audience"] == audience]
    if audience == "business":
        rows = [a for a in rows if a.get("businessId") == (business_id or BUSINESS_ID)]
    if cuisine:
        rows = [a for a in rows if a.get("cuisine") in (None, cuisine)]
    read = store.read_ids([a["id"] for a in rows])
    out = []
    for a in rows:
        distance = round(geo.miles_between(lat, lng, a["lat"], a["lng"]), 2) if lat is not None and lng is not None else None
        if audience == "consumer" and distance is not None and distance > radius_mi:
            continue
        out.append({"id": a["id"], "kind": a["kind"], "audience": a["audience"], "spotId": a["spotId"], "cuisine": a["cuisine"],
                    "title": a["title"], "detail": a["detail"], "distanceMi": distance,
                    "createdAt": (now - timedelta(minutes=a["minutesAgo"])).isoformat(timespec="seconds"),
                    "read": a["id"] in read, "demo": True})
    return sorted(out, key=lambda a: a["createdAt"], reverse=True)


def business_you() -> dict:
    return copy.deepcopy(_load("business.json")["you"])


def seed() -> None:
    """Create the demo business and keep 30 demo picks inside the last 7 days."""
    business = _load("business.json")
    if not store.get_business(BUSINESS_ID):
        store.create_business(name=business["name"], business_type=business["cuisine"], location=f"{business['area']}, Seattle",
                              address="E Olive Way, Seattle, WA", lat=config.CAPITOL_HILL["lat"], lng=config.CAPITOL_HILL["lng"],
                              business_id=BUSINESS_ID, demo=True, profile={"businessType": "Sushi bar", "location": business["area"]})
        store.update_business(BUSINESS_ID, spot_id=BUSINESS_ID, scoring_status="complete")
        store.set_goals(BUSINESS_ID, business["goals"])
    store.update_business(BUSINESS_ID, share_stock_alerts=1)  # the demo shop shares fresh-stock alerts

    cuisine = business["cuisine"]
    since = datetime.now(timezone.utc) - timedelta(days=7)
    recent = [p for p in store.picks_since(cuisine, since, include_demo=True) if p["demo"]]
    if len(recent) >= 30:
        return
    store.clear_demo_picks(cuisine)
    rivals = list(business["seedPicks"]["lostTo"])
    chosen = [BUSINESS_ID] * business["seedPicks"]["won"]
    for spot_id, n in business["seedPicks"]["lostTo"].items():
        chosen += [spot_id] * n
    now = datetime.now(timezone.utc)
    for i, spot_id in enumerate(chosen):
        # Every comparison includes the demo business, the chosen spot and one more rival.
        extra = rivals[(i + 1) % len(rivals)]
        compared = list(dict.fromkeys([BUSINESS_ID, spot_id, extra]))
        when = (now - timedelta(hours=5 + i * 5.3)).isoformat(timespec="seconds")
        store.add_pick(cuisine, spot_id, compared, demo=True, created_at=when)
