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

def fetch_square(days: int = 56) -> list[dict]:
    token = os.environ.get("SQUARE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("SQUARE_ACCESS_TOKEN is not set")
    host = SQUARE_HOSTS[os.environ.get("SQUARE_ENVIRONMENT", "production")]
    headers = {"Authorization": f"Bearer {token}", "Square-Version": SQUARE_VERSION}

    with httpx.Client(base_url=host, headers=headers, timeout=30) as http:
        location_id = os.environ.get("SQUARE_LOCATION_ID")
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

def fetch_toast(days: int = 56) -> list[dict]:
    client_id, secret = os.environ.get("TOAST_CLIENT_ID"), os.environ.get("TOAST_CLIENT_SECRET")
    guid = os.environ.get("TOAST_RESTAURANT_GUID")
    if not (client_id and secret and guid):
        raise RuntimeError("TOAST_CLIENT_ID, TOAST_CLIENT_SECRET and TOAST_RESTAURANT_GUID must be set")
    host = os.environ.get("TOAST_API_HOST", TOAST_HOST)

    with httpx.Client(base_url=host, timeout=30) as http:
        login = http.post("/authentication/v1/authentication/login", json={
            "clientId": client_id, "clientSecret": secret, "userAccessType": "TOAST_MACHINE_CLIENT",
        }).raise_for_status().json()
        http.headers.update({
            "Authorization": f"Bearer {login['token']['accessToken']}",
            "Toast-Restaurant-External-ID": guid,
        })
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
