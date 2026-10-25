"""Pull item-level sales from a point-of-sale system (Square or Toast).

Both return rows in the same shape as a Square "Items" CSV export
(Date, Time, Category, Item, Qty, Gross Sales), in the business's local
time, so business_agent.analyze_rows works the same for every source.

Credentials come from .env:
  Square: SQUARE_ACCESS_TOKEN, SQUARE_ENVIRONMENT (sandbox|production),
          SQUARE_LOCATION_ID (optional; defaults to the first location)
  Toast:  TOAST_CLIENT_ID, TOAST_CLIENT_SECRET, TOAST_RESTAURANT_GUID,
          TOAST_API_HOST (optional; defaults to production)
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

SQUARE_VERSION = "2026-09-16"
SQUARE_HOSTS = {
    "production": "https://connect.squareup.com",
    "sandbox": "https://connect.squareupsandbox.com",
}
TOAST_HOST = "https://ws-api.toasttab.com"


def _row(local: datetime, item: str, qty: float, gross: float, category: str | None = None) -> dict:
    return {
        "Date": local.date().isoformat(),
        "Time": local.strftime("%H:%M:%S"),
        "Category": category or "",
        "Item": item,
        "Qty": qty,
        "Gross Sales": gross,
    }


def _parse_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- Square ----------

def _square_client(token: str | None, environment: str | None) -> httpx.Client:
    token = token or os.environ.get("SQUARE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("SQUARE_ACCESS_TOKEN is not set")
    environment = environment or os.environ.get("SQUARE_ENVIRONMENT", "production")
    if environment not in SQUARE_HOSTS:
        raise ValueError(f"Unknown Square environment: {environment}")
    headers = {"Authorization": f"Bearer {token}", "Square-Version": SQUARE_VERSION}
    return httpx.Client(base_url=SQUARE_HOSTS[environment], headers=headers, timeout=30)


def check_square(token: str, environment: str = "production") -> list[dict]:
    """The account's locations ({id, name}), proving the token works. Raises on a bad token."""
    with _square_client(token, environment) as http:
        locations = http.get("/v2/locations").raise_for_status().json().get("locations", [])
    return [{"id": loc["id"], "name": loc.get("name")} for loc in locations]


def fetch_square(days: int = 56, *, token: str | None = None, environment: str | None = None,
                 location_id: str | None = None) -> list[dict]:
    """Item-level rows. Credentials default to .env (SQUARE_*); pass them to use a specific owner's account."""
    with _square_client(token, environment) as http:
        location_id = location_id or os.environ.get("SQUARE_LOCATION_ID")
        if location_id:
            location = http.get(f"/v2/locations/{location_id}").raise_for_status().json()["location"]
        else:
            locations = http.get("/v2/locations").raise_for_status().json().get("locations", [])
            if not locations:
                raise RuntimeError("No Square locations found for this account")
            location = locations[0]
        tz = ZoneInfo(location.get("timezone") or "UTC")

        end = datetime.now(timezone.utc)
        body = {
            "location_ids": [location["id"]],
            "limit": 500,
            "query": {
                "filter": {
                    "date_time_filter": {"closed_at": {
                        "start_at": (end - timedelta(days=days)).isoformat(),
                        "end_at": end.isoformat(),
                    }},
                    "state_filter": {"states": ["COMPLETED"]},
                },
                "sort": {"sort_field": "CLOSED_AT", "sort_order": "ASC"},
            },
        }
        orders = []
        while True:
            page = http.post("/v2/orders/search", json=body).raise_for_status().json()
            orders.extend(page.get("orders", []))
            if not page.get("cursor"):
                break
            body["cursor"] = page["cursor"]
    print(f"[square] {len(orders)} orders from {location.get('name')}", file=sys.stderr)
    return square_orders_to_rows(orders, tz)


def square_orders_to_rows(orders: list[dict], tz: ZoneInfo) -> list[dict]:
    rows = []
    for order in orders:
        when = order.get("closed_at") or order.get("created_at")
        if not when:
            continue
        local = _parse_utc(when).astimezone(tz)
        for li in order.get("line_items", []):
            qty = float(li.get("quantity") or 0)
            if qty <= 0:
                continue
            money = li.get("gross_sales_money") or {}
            if "amount" in money:
                gross = money["amount"] / 100
            else:  # fall back to unit price x quantity
                gross = (li.get("base_price_money") or {}).get("amount", 0) / 100 * qty
            name = li.get("name") or "Custom amount"
            if li.get("variation_name") and li["variation_name"] != "Regular":
                name = f"{name} ({li['variation_name']})"
            rows.append(_row(local, name, qty, gross))
    return rows


# ---------- Toast ----------

def _toast_session(client_id: str | None, client_secret: str | None, guid: str | None,
                   host: str | None) -> httpx.Client:
    """A logged-in Toast client for one restaurant. Credentials default to .env (TOAST_*)."""
    client_id = client_id or os.environ.get("TOAST_CLIENT_ID")
    client_secret = client_secret or os.environ.get("TOAST_CLIENT_SECRET")
    guid = guid or os.environ.get("TOAST_RESTAURANT_GUID")
    if not (client_id and client_secret and guid):
        raise RuntimeError("TOAST_CLIENT_ID, TOAST_CLIENT_SECRET and TOAST_RESTAURANT_GUID must be set")
    http = httpx.Client(base_url=host or os.environ.get("TOAST_API_HOST", TOAST_HOST), timeout=30)
    try:
        login = http.post("/authentication/v1/authentication/login", json={
            "clientId": client_id, "clientSecret": client_secret, "userAccessType": "TOAST_MACHINE_CLIENT",
        }).raise_for_status().json()
    except Exception:
        http.close()
        raise
    http.headers.update({
        "Authorization": f"Bearer {login['token']['accessToken']}",
        "Toast-Restaurant-External-ID": guid,
    })
    return http


def check_toast(client_id: str, client_secret: str, guid: str, host: str | None = None) -> dict:
    """{name} of the restaurant, proving the credentials work. Raises on bad credentials."""
    with _toast_session(client_id, client_secret, guid, host) as http:
        try:
            info = http.get(f"/restaurants/v1/restaurants/{guid}").raise_for_status().json()
            return {"name": (info.get("general") or {}).get("name")}
        except httpx.HTTPError:
            return {"name": None}  # logged in; the restaurant details are optional


def fetch_toast(days: int = 56, *, client_id: str | None = None, client_secret: str | None = None,
                guid: str | None = None, host: str | None = None) -> list[dict]:
    """Item-level rows. Credentials default to .env (TOAST_*); pass them to use a specific owner's account."""
    guid = guid or os.environ.get("TOAST_RESTAURANT_GUID")
    with _toast_session(client_id, client_secret, guid, host) as http:
        try:
            info = http.get(f"/restaurants/v1/restaurants/{guid}").raise_for_status().json()
            tz = ZoneInfo(info["general"]["timeZone"])
        except Exception:
            tz = ZoneInfo(os.environ.get("TOAST_TIMEZONE", "America/Los_Angeles"))

        end = datetime.now(timezone.utc)
        params = {
            "startDate": (end - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
            "endDate": end.strftime("%Y-%m-%dT%H:%M:%S.000+0000"),
            "pageSize": 100,
        }
        orders, page = [], 1
        while True:
            batch = http.get("/orders/v2/ordersBulk", params={**params, "page": page}).raise_for_status().json()
            orders.extend(batch)
            if len(batch) < params["pageSize"]:
                break
            page += 1
            time.sleep(0.25)  # Toast allows 5 requests per second per location
    print(f"[toast] {len(orders)} orders", file=sys.stderr)
    return toast_orders_to_rows(orders, tz)


def toast_orders_to_rows(orders: list[dict], tz: ZoneInfo) -> list[dict]:
    rows = []
    for order in orders:
        if order.get("voided") or order.get("deleted"):
            continue
        when = order.get("closedDate") or order.get("openedDate")
        if not when:
            continue
        local = _parse_utc(when).astimezone(tz)
        for check in order.get("checks", []):
            if check.get("voided") or check.get("deleted"):
                continue
            for sel in check.get("selections", []):
                qty = float(sel.get("quantity") or 0)
                if sel.get("voided") or qty <= 0:
                    continue
                gross = sel.get("preDiscountPrice")
                if gross is None:
                    gross = sel.get("price") or 0
                rows.append(_row(local, sel.get("displayName") or "Unknown item", qty, float(gross)))
    return rows
