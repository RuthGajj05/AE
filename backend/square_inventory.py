"""Square IN_STOCK counts for one location: a Python port of Manny's fetchSquareInventory (main: lib/square.ts).

Same rules: only variations with inventory tracking on (location overrides win), only items present at the
location, the newest IN_STOCK count per variation, and a missing count means unknown, not zero. Square has
no push for counts here, so alerts compare each fetch with the last saved snapshot.

Env: SQUARE_ACCESS_TOKEN, SQUARE_ENVIRONMENT (sandbox | production, default sandbox), SQUARE_LOCATION_ID (optional;
defaults to the first active location).
"""

import os
import re

import httpx

SQUARE_API_VERSION = "2026-09-16"  # same as lib/square.ts and Ruth's agent/pos.py
HOSTS = {"production": "https://connect.squareup.com", "sandbox": "https://connect.squareupsandbox.com"}
MAX_PAGES = 100
_QUANTITY = re.compile(r"^-?\d+(?:\.\d{1,5})?$")


class SquareError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("SQUARE_ACCESS_TOKEN", "").strip())


def _present_at(value: dict, location_id: str) -> bool:
    # Square defaults present_at_all_locations to true; ITEM and ITEM_VARIATION settings both apply.
    if value.get("present_at_all_locations") is False:
        return location_id in (value.get("present_at_location_ids") or [])
    return location_id not in (value.get("absent_at_location_ids") or [])


def fetch_inventory(location_id: str | None = None, client: httpx.Client | None = None) -> dict:
    """{"locationId", "items": [{variationId, name, quantity (float or None)}]} for tracked items."""
    token = os.environ.get("SQUARE_ACCESS_TOKEN", "").strip()
    if not token:
        raise SquareError("SQUARE_ACCESS_TOKEN is not set in backend/.env.")
    environment = os.environ.get("SQUARE_ENVIRONMENT", "").strip() or "sandbox"
    if environment not in HOSTS:
        raise SquareError("SQUARE_ENVIRONMENT must be sandbox or production.")
    http = client or httpx.Client(timeout=30)
    headers = {"Authorization": f"Bearer {token}", "Square-Version": SQUARE_API_VERSION, "Accept": "application/json"}

    def request(path: str, body: dict | None = None) -> dict:
        resp = http.request("POST" if body is not None else "GET", f"{HOSTS[environment]}{path}", json=body, headers=headers)
        if resp.status_code in (401, 403):
            raise SquareError("Square rejected the access token or it lacks inventory, item and location read permissions.")
        if resp.status_code >= 400:
            raise SquareError(f"Square could not complete the inventory request ({resp.status_code}).")
        return resp.json()

    location_id = location_id or os.environ.get("SQUARE_LOCATION_ID") or None
    active = [loc["id"] for loc in request("/v2/locations").get("locations", []) if loc.get("status") == "ACTIVE"]
    if not active:
        raise SquareError("This Square account has no active locations.")
    location_id = location_id or active[0]
    if location_id not in active:
        raise SquareError("That Square location is not active or not on this account.")

    parents: dict[str, dict] = {}
    variations: dict[str, dict] = {}
    cursor, pages = None, 0
    while True:
        pages += 1
        if pages > MAX_PAGES:
            raise SquareError("This Square catalog is too large to load in one refresh.")
        page = request("/v2/catalog/list?types=ITEM,ITEM_VARIATION" + (f"&cursor={cursor}" if cursor else ""))
        for obj in page.get("objects", []):
            if obj.get("is_deleted"):
                continue
            if obj.get("type") == "ITEM":
                parents[obj["id"]] = obj
                for v in (obj.get("item_data") or {}).get("variations", []):
                    if not v.get("is_deleted"):
                        variations[v["id"]] = v
            elif obj.get("type") == "ITEM_VARIATION":
                variations[obj["id"]] = obj
        cursor = page.get("cursor")
        if not cursor:
            break

    tracked: dict[str, str] = {}
    for vid, v in variations.items():
        data = v.get("item_variation_data") or {}
        parent = parents.get(data.get("item_id"))
        if not parent or not _present_at(parent, location_id) or not _present_at(v, location_id):
            continue
        override = next((o for o in data.get("location_overrides", []) if o.get("location_id") == location_id), {})
        if override.get("track_inventory", data.get("track_inventory", False)) is not True:
            continue
        item_name = (parent.get("item_data") or {}).get("name") or "Unnamed item"
        variation_name = data.get("name") or "Regular"
        tracked[vid] = item_name if variation_name == "Regular" else f"{item_name} ({variation_name})"

    counts: dict[str, tuple[float, str]] = {}
    ids = list(tracked)
    for offset in range(0, len(ids), 1000):
        cursor = None
        while True:
            body = {"catalog_object_ids": ids[offset:offset + 1000], "location_ids": [location_id], "states": ["IN_STOCK"], "limit": 1000}
            page = request("/v2/inventory/counts/batch-retrieve", {**body, **({"cursor": cursor} if cursor else {})})
            for c in page.get("counts", []):
                vid, qty = c.get("catalog_object_id"), c.get("quantity")
                if c.get("location_id") != location_id or c.get("state") != "IN_STOCK" or vid not in tracked:
                    continue
                if not isinstance(qty, str) or not _QUANTITY.match(qty):
                    raise SquareError("Square returned an unreadable stock count.")
                when = c.get("calculated_at") or ""
                if vid not in counts or when > counts[vid][1]:
                    counts[vid] = (float(qty), when)
            cursor = page.get("cursor")
            if not cursor:
                break

    items = [{"variationId": vid, "name": name, "quantity": counts[vid][0] if vid in counts else None} for vid, name in tracked.items()]
    return {"locationId": location_id, "items": sorted(items, key=lambda i: (i["name"], i["variationId"]))}
