"""crumbs alerts from three sources, in one shape (backend/API.md → Alerts):

1. Ruth's monitor (agent/monitor.py, reused as-is): it re-researches a business's tracked competitors, has
   Claude diff the snapshots and records changes (new_competitor, closed, price_change, hours_change,
   rating_change, review_trend). Owners get every change for their business; consumers get the public
   ones (new spot, closed, price change) without the owner-only "why it matters" note. With SUPABASE_URL
   and SUPABASE_SERVICE_ROLE_KEY set, the monitor uses Ruth's SupabaseStore and changes are read from her
   Supabase `changes` table; otherwise MonitorStore below keeps them in SQLite through store.py.
2. Square inventory (square_inventory.py, ported from Manny's lib/square.ts): a tracked item whose IN_STOCK
   count rises by a meaningful amount since the last snapshot is a public "fresh_stock" alert, only for
   businesses that opted in and never with counts; dropping below the owner's threshold is a "low_stock"
   alert for the owner only.
3. Our own scores: a spot newly #1 for an attribute in its food type and area is a public "top_rated" alert.

Read state lives in SQLite (alert_reads). Consumers are anonymous, so a consumer alert's read flag is shared.
"""

import sys
from datetime import datetime, timedelta, timezone

import config
import cuisines
import emails
import geo
import scoring
import square_inventory
import store

# A restock is "meaningful" when it adds at least this many units and at least this share of the previous count.
FRESH_MIN_UNITS = 10
FRESH_MIN_SHARE = 0.5
ALERT_DAYS = 14
MAX_ALERTS = 50

PUBLIC_CHANGES = {"new_competitor": "new_spot", "closed": "closed", "price_change": "price_change"}
OWNER_TITLES = {
    "new_competitor": "New competitor nearby: {name}",
    "closed": "{name} has closed",
    "price_change": "{name} changed a price",
    "hours_change": "{name} changed its hours",
    "rating_change": "{name}'s rating moved",
    "review_trend": "Review trend at {name}",
    "other": "Change at {name}",
}
PUBLIC_TITLES = {"new_spot": "New spot: {name}", "closed": "{name} has closed", "price_change": "Price change at {name}"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(when: datetime) -> str:
    return when.isoformat(timespec="seconds")


def _clip(text: str, n: int = 280) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


# ---------- 2. Square stock ----------

def stock_events(previous: dict[str, float | None], items: list[dict], threshold: float) -> list[dict]:
    """Compare a fresh inventory fetch with the last snapshot. Unknown counts never trigger anything.

    fresh: count rose by ≥ FRESH_MIN_UNITS and ≥ FRESH_MIN_SHARE of the previous count (0 → 12 is fresh, 20 → 25 isn't).
    low:   count crossed below the owner's threshold (or starts below it on the first snapshot); stays quiet while low.
    """
    events = []
    for item in items:
        now = item.get("quantity")
        if now is None:
            continue
        before = previous.get(item["variationId"])
        if before is not None and now - before >= max(FRESH_MIN_UNITS, before * FRESH_MIN_SHARE):
            events.append({"type": "fresh", "variationId": item["variationId"], "name": item["name"], "before": before, "now": now})
        if now < threshold and (before is None or before >= threshold):
            events.append({"type": "low", "variationId": item["variationId"], "name": item["name"], "before": before, "now": now})
    return events


def shares_stock_alerts(business: dict, goals: list[str]) -> bool:
    """Opt-in for public fresh-stock alerts: the business setting, or a goal saying so. Off by default."""
    return bool(business.get("share_stock_alerts")) or any("share stock" in g.lower() or g == "share_stock_alerts" for g in goals)


def _units(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def _item_phrase(name: str) -> str:
    """"Bluefin Toro" → "bluefin toro" for a sentence; all-caps names (brands, acronyms) stay as they are."""
    return name if name.isupper() else name.lower()


def stock_alerts(business: dict, goals: list[str], events: list[dict], *, when: datetime | None = None) -> list[dict]:
    when = when or _now()
    day = when.date().isoformat()
    threshold = business.get("low_stock_threshold", 5)
    share = shares_stock_alerts(business, goals)
    out = []
    for e in events:
        if e["type"] == "low":
            out.append({
                "kind": "low_stock", "audience": "business", "business_id": business["id"], "spot_id": business.get("spot_id"),
                "cuisine": business.get("business_type"), "lat": business.get("lat"), "lng": business.get("lng"),
                "title": f"Low stock: {e['name']}",
                "detail": f"{_units(e['now'])} left (your alert level is {_units(threshold)}). Reorder or mark it sold out.",
                "dedupe_key": f"low:{business['id']}:{e['variationId']}:{day}", "created_at": _iso(when),
            })
        elif e["type"] == "fresh" and share:
            # Public: no counts, ever. Only the fact that something was restocked.
            out.append({
                "kind": "fresh_stock", "audience": "consumer", "business_id": business["id"], "spot_id": business.get("spot_id"),
                "cuisine": business.get("business_type"), "lat": business.get("lat"), "lng": business.get("lng"),
                "title": f"{business['name']} just got a fresh shipment of {_item_phrase(e['name'])}",
                "detail": "Restocked today. Worth a visit while it's fresh.",
                "dedupe_key": f"fresh:{business['id']}:{e['variationId']}:{day}", "created_at": _iso(when),
            })
    return out


def check_stock(business_id: str) -> dict:
    """Fetch Square counts for this business, record alerts, save the snapshot."""
    b = store.get_business(business_id)
    if not b:
        raise ValueError("No such business.")
    inventory = square_inventory.fetch_inventory()
    previous = {vid: row["quantity"] for vid, row in store.get_inventory(business_id).items()}
    events = stock_events(previous, inventory["items"], b.get("low_stock_threshold", 5))
    added = sum(store.add_alert(a) for a in stock_alerts(b, store.get_goals(business_id), events))
    store.save_inventory(business_id, [i for i in inventory["items"] if i["quantity"] is not None])
    return {"items": len(inventory["items"]), "events": len(events), "alertsAdded": added}


# ---------- 3. Top rated ----------

def top_rated_alerts(cuisine: str, area_key: str, previous: list[dict] | None, current: list[dict],
                     *, when: datetime | None = None) -> list[dict]:
    """A public alert for each attribute whose #1 spot changed since the last scoring of this area."""
    when = when or _now()
    attrs = cuisines.compare_attributes(cuisine)
    by_attr = {a["id"]: a for a in attrs}
    by_spot = {s["id"]: s for s in current}
    food = cuisines.get(cuisine)["label"].lower()
    out = []
    for attr_id, spot_id in scoring.new_leaders(previous, current, attrs).items():
        spot, attr = by_spot[spot_id], by_attr[attr_id]
        value = scoring.metric_value(spot, attr_id)
        if attr_id == "wait":
            title = f"{spot['name']} now has the shortest wait"
            detail = f"About {value} min, the shortest of {len(current)} {food} spots nearby, from what reviewers say."
        elif attr_id == "ambiance":
            title = f"{spot['name']} now has the best vibe"
            detail = f"{value}% of ambiance mentions are positive, the best of {len(current)} {food} spots nearby."
        else:
            title = f"{spot['name']} is now #1 for {attr['label'].lower()}"
            line = (spot.get("_highlights") or {}).get(attr_id) or spot.get("reason") or ""
            detail = f"Top {attr['label'].lower()} score ({value}/100) among {len(current)} {food} spots nearby. {line}".strip()
        out.append({
            "kind": "top_rated", "audience": "consumer", "spot_id": spot_id, "cuisine": cuisine,
            "lat": spot.get("lat"), "lng": spot.get("lng"), "title": title, "detail": _clip(detail),
            "dedupe_key": f"top:{area_key}:{attr_id}:{spot_id}:{when.date().isoformat()}", "created_at": _iso(when),
        })
    return out


# ---------- 1. Ruth's monitor ----------

def supabase_configured() -> bool:
    return config.has_key("SUPABASE_URL") and config.has_key("SUPABASE_SERVICE_ROLE_KEY")


def _monitor_module():
    """agent/monitor.py imports its siblings by bare name (import competitor_agent), so agent/ goes on the path."""
    agent_dir = str(config.REPO_ROOT / "agent")
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    import monitor
    return monitor


def _supabase():
    return _monitor_module().SupabaseStore()


class MonitorStore:
    """Ruth's monitor store interface (start_run … queue_notifications), backed by SQLite through store.py."""

    def start_run(self, business: dict) -> str:
        return store.start_monitor_run(business["id"])

    def finish_run(self, run_id, *, error=None, changes=0, baseline=False) -> None:
        store.finish_monitor_run(run_id, error=error, changes=changes, baseline=baseline)

    def latest_snapshot(self, business: dict) -> dict | None:
        snap = store.latest_snapshot(business["id"])
        if not snap or not isinstance(snap["data"], dict) or "competitors" not in snap["data"]:
            return None
        return {**snap["data"], "_id": snap["id"]}

    def save_snapshot(self, business: dict, data: dict, run_id) -> str:
        store.upsert_competitors(business["id"], data.get("competitors", []))
        return store.save_snapshot(data, business_id=business["id"])

    def save_changes(self, business, changes, run_id, snapshot_id, previous_snapshot_id) -> None:
        store.save_changes(business["id"], changes, run_id=run_id, snapshot_id=snapshot_id, previous_snapshot_id=previous_snapshot_id)

    def queue_notifications(self, business: dict, title: str, message: str, run_id) -> None:
        # Each change is already an in-app alert (from the changes table); this emails the owner the summary.
        emails.send_alert(business["id"], title, message)


def uses_supabase(business: dict | None) -> bool:
    """A business linked to Ruth's Supabase project keeps its monitor data there; every other one (including all
    businesses onboarded in the app) uses SQLite, even when Supabase is configured."""
    return bool(business and business.get("supabase_business_id")) and supabase_configured()


def run_monitor(business_id: str) -> dict:
    """Run Ruth's monitor for one crumbs business. The first run saves a baseline; later runs record changes as
    alerts and email the owner a summary."""
    b = store.get_business(business_id)
    if not b:
        raise ValueError("No such business.")
    monitor = _monitor_module()
    if uses_supabase(b):
        sb = monitor.SupabaseStore()
        report = monitor.check(sb.get_business(b["supabase_business_id"]), sb)
    else:
        ruth_business = {"id": business_id, "name": b["name"], "business_type": cuisines.research_type(b),
                         "location": b["address"] or b["location"]}
        report = monitor.check(ruth_business, MonitorStore())
    return {"baseline": report is None, "changes": len(report.changes) if report else 0}


def _supabase_changes(business: dict | None, *, public_only: bool, since: str) -> list[dict]:
    params = {"created_at": f"gte.{since}", "order": "created_at.desc", "limit": 100, "select": "*"}
    if business is not None:
        params["business_id"] = f"eq.{business['supabase_business_id']}"
    if public_only:
        params["kind"] = f"in.({','.join(PUBLIC_CHANGES)})"
    try:
        return _supabase()._get("changes", params)
    except Exception as e:  # Supabase down: SQLite alerts still show
        print(f"[alerts] Supabase changes unavailable: {e}", file=sys.stderr)
        return []


def _changes_for(business: dict | None, *, public_only: bool, since: str) -> list[dict]:
    """One business's changes from wherever its monitor runs; for the public feed, both stores."""
    if business is not None and uses_supabase(business):
        return _supabase_changes(business, public_only=public_only, since=since)
    local = store.list_changes(business_id=business["id"] if business else None,
                               kinds=list(PUBLIC_CHANGES) if public_only else None, since=since)
    if business is None and supabase_configured():
        local = [*local, *_supabase_changes(None, public_only=public_only, since=since)]
    return local


def _place(change: dict) -> tuple[str | None, float | None, float | None]:
    """(spot id, lat, lng) for the competitor a change is about: a scored spot by name, else its geocoded address."""
    spot = store.find_spot_by_name(change["competitor_name"])
    if spot:
        return spot["id"], spot["lat"], spot["lng"]
    row = store.competitor_by_name(change["business_id"], change["competitor_name"])  # None for Supabase changes
    if row:
        point = geo.geocode(row["address"]) if row and row.get("address") else None
        if point:
            return None, *point
    return None, None, None


def change_alert(change: dict, audience: str, cuisine: str | None) -> dict:
    spot_id, lat, lng = _place(change)
    name, before, after = change["competitor_name"], change.get("before") or "", change.get("after") or ""
    if audience == "business":
        kind = change["kind"]
        title = OWNER_TITLES.get(kind, OWNER_TITLES["other"]).format(name=name)
        moved = f"{before} → {after}." if before and before != "none" else f"{after}."
        detail = _clip(f"{moved} {change.get('why_it_matters') or ''}")
    else:
        kind = PUBLIC_CHANGES[change["kind"]]
        title = PUBLIC_TITLES[kind].format(name=name)
        detail = _clip(f"{before} → {after}" if kind == "price_change" and before else after or "From recent listings.")
    return {"id": f"chg-{change['id']}", "kind": kind, "audience": audience, "spot_id": spot_id, "cuisine": cuisine,
            "title": title, "detail": detail, "lat": lat, "lng": lng, "created_at": change["created_at"]}


# ---------- reading ----------

def _public(alert: dict, center: tuple[float, float] | None, read: set[str]) -> dict:
    distance = None
    if center and alert.get("lat") is not None and alert.get("lng") is not None:
        distance = round(geo.miles_between(center[0], center[1], alert["lat"], alert["lng"]), 2)
    return {"id": alert["id"], "kind": alert["kind"], "audience": alert["audience"], "spotId": alert.get("spot_id"),
            "cuisine": alert.get("cuisine"), "title": alert["title"], "detail": alert["detail"], "distanceMi": distance,
            "createdAt": alert["created_at"], "read": alert["id"] in read}


def list_alerts(*, audience: str, lat: float | None, lng: float | None, radius_mi: float,
                business: dict | None = None, cuisine: str | None = None) -> list[dict]:
    since = _iso(_now() - timedelta(days=ALERT_DAYS))
    if audience == "business":
        raw = [change_alert(c, "business", business["business_type"]) for c in _changes_for(business, public_only=False, since=since)]
        raw += store.list_alerts(audience="business", business_id=business["id"], since=since)
        center = (lat, lng) if lat is not None and lng is not None else (
            (business["lat"], business["lng"]) if business.get("lat") is not None else None)
    else:
        seen, raw = set(), []
        for c in _changes_for(None, public_only=True, since=since):
            key = (c["kind"], c["competitor_name"].lower(), (c.get("after") or "").lower())
            if key not in seen:  # several owners' monitors can report the same public change
                seen.add(key)
                raw.append(change_alert(c, "consumer", None))
        raw += store.list_alerts(audience="consumer", since=since)
        center = (lat, lng)
    if cuisine:
        raw = [a for a in raw if a.get("cuisine") in (None, cuisine)]
    read = store.read_ids([a["id"] for a in raw])
    alerts = [_public(a, center, read) for a in raw]
    if audience == "consumer":
        # Public alerts are about places, so they must be on the map and inside the circle.
        alerts = [a for a in alerts if a["distanceMi"] is not None and a["distanceMi"] <= radius_mi]
    return sorted(alerts, key=lambda a: a["createdAt"], reverse=True)[:MAX_ALERTS]
