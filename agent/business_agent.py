"""Analyzes the owner's own business.

Two parts:
- analyze_sales: plain-Python analysis of a Square "Items" sales export (CSV),
  so every number is computed, not estimated by the model.
- research_presence: a Claude agent that looks up the business's own reviews,
  menu and hours online.

Usage:
    python agent/business_agent.py "Test Bakery" "Capitol Hill, Seattle" --sales data/sample_sales.csv
"""

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from anthropic import beta_tool

from agent_loop import run_agent
from competitor_agent import read_pages, search_web

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _money(s: str | float) -> float:
    if isinstance(s, (int, float)):
        return float(s)
    return float(s.replace("$", "").replace(",", "").strip() or 0)


def _hhmm(minutes: float) -> str:
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}"


def analyze_sales(csv_path: str) -> dict:
    """Summarize a Square "Items" export with columns Date, Time, Item, Qty, Gross Sales (Category optional)."""
    with open(csv_path, newline="") as f:
        return analyze_rows(list(csv.DictReader(f)))


def analyze_rows(rows: list[dict]) -> dict:
    """Summarize item-level sales rows (from a CSV export or pos.fetch_square/fetch_toast)."""
    if not rows:
        raise ValueError("No sales rows to analyze")

    days: set[str] = set()
    day_revenue: dict[str, float] = defaultdict(float)
    day_first_sale: dict[str, int] = {}
    day_last_sale: dict[str, int] = {}
    hour_revenue: Counter = Counter()
    items: dict[str, dict] = defaultdict(lambda: {
        "qty": 0, "revenue": 0.0, "category": None, "days": set(), "last_sale": defaultdict(int),
        "daily_units": defaultdict(int),
    })

    for r in rows:
        d = r["Date"]
        t = datetime.strptime(r["Time"], "%H:%M:%S")
        mins = t.hour * 60 + t.minute
        qty, revenue = float(r["Qty"]), _money(r["Gross Sales"])
        days.add(d)
        day_revenue[d] += revenue
        day_first_sale[d] = min(day_first_sale.get(d, 24 * 60), mins)
        day_last_sale[d] = max(day_last_sale.get(d, 0), mins)
        hour_revenue[t.hour] += revenue
        it = items[r["Item"]]
        it["qty"] += qty
        it["revenue"] += revenue
        it["category"] = r.get("Category")
        it["days"].add(d)
        it["last_sale"][d] = max(it["last_sale"][d], mins)
        it["daily_units"][d] += qty

    n_days = len(days)
    sorted_days = sorted(days)
    first, last = datetime.fromisoformat(sorted_days[0]), datetime.fromisoformat(sorted_days[-1])
    weeks = ((last - first).days + 1) / 7
    open_weekdays = sorted({datetime.fromisoformat(d).weekday() for d in days})
    store_close = statistics.median(day_last_sale.values())
    total = sum(day_revenue.values())

    weekday_rev: dict[int, list[float]] = defaultdict(list)
    for d, rev in day_revenue.items():
        weekday_rev[datetime.fromisoformat(d).weekday()].append(rev)

    item_stats = []
    for name, it in items.items():
        median_last = statistics.median(it["last_sale"].values())
        sold_share = len(it["days"]) / n_days
        units = list(it["daily_units"].values())
        units_cv = statistics.pstdev(units) / statistics.mean(units)
        item_stats.append({
            "item": name,
            "category": it["category"],
            "avg_price": round(it["revenue"] / it["qty"], 2),
            "units": round(it["qty"], 2),
            "revenue": round(it["revenue"], 2),
            "revenue_share_pct": round(100 * it["revenue"] / total, 1),
            "avg_units_per_open_day": round(it["qty"] / n_days, 1),
            "typical_last_sale": _hhmm(median_last),
            "daily_units_min_max": [min(units), max(units)],
            # Sells almost the same number every day, even on busier weekends, and stops
            # selling 2+ hours before closing: it is probably hitting its batch size.
            "likely_sells_out": sold_share >= 0.8 and units_cv < 0.08 and median_last <= store_close - 120,
        })
    item_stats.sort(key=lambda x: x["revenue"], reverse=True)

    return {
        "period": f"{sorted_days[0]} to {sorted_days[-1]}",
        "days_with_sales": n_days,
        "open_weekdays": [WEEKDAYS[w] for w in open_weekdays],
        "closed_weekdays": [WEEKDAYS[w] for w in range(7) if w not in open_weekdays],
        "open_days_per_month": round(n_days / weeks * 4.33, 1),
        "typical_first_sale": _hhmm(statistics.median(day_first_sale.values())),
        "typical_last_sale": _hhmm(store_close),
        "total_revenue": round(total, 2),
        "avg_revenue_per_open_day": round(total / n_days, 2),
        "avg_revenue_by_weekday": {
            WEEKDAYS[w]: round(statistics.mean(v), 2) for w, v in sorted(weekday_rev.items())
        },
        "revenue_by_hour": {f"{h:02d}:00": round(v, 2) for h, v in sorted(hour_revenue.items())},
        "items": item_stats,
    }


@beta_tool
def submit_business_profile(
    found_online: bool,
    rating: float | None,
    review_count: int | None,
    praised_for: list[str],
    complaints: list[str],
    online_menu_and_prices: list[str],
    online_hours: str | None,
    presence_gaps: list[str],
    sources: list[str],
) -> str:
    """Submit what you found about the business online. Call this exactly once.

    Args:
        found_online: Whether you found any listing, website or reviews for this exact business.
        rating: Average star rating, if found.
        review_count: Number of reviews, if found.
        praised_for: Recurring positives in its reviews.
        complaints: Recurring negatives in its reviews.
        online_menu_and_prices: Items and prices as listed online, e.g. "Croissant: $4.00".
        online_hours: Hours as listed online.
        presence_gaps: Problems with its online presence, e.g. "No Google listing", "Website has no menu", "Hours on Yelp are out of date".
        sources: URLs this is based on.
    """
    return "Profile received."


PRESENCE_SYSTEM = """You look up a small business's own online presence so its owner can see how customers find and judge it.

Search for the business by name and location: its website, Google/Yelp/TripAdvisor listings, reviews, menu, prices and hours. Use search_web (purpose="reviews" for reviews) and read_pages for its own website. Yelp and TripAdvisor pages can't be read with read_pages, only their search snippets.

Make sure results are about this exact business at this location, not a similarly named one. If you can't find it after a few searches, it may be new or not listed: submit with found_online=false and list that as a presence gap rather than searching further.

Google Maps listings and Google ratings rarely appear in these web search results, so not finding one does not mean the business has no Google listing. The same goes for any other site: only call something missing if you have positive evidence (e.g. the business's own site says it has no menu). Otherwise phrase it as unverified, e.g. "Couldn't confirm a Google Business listing; check it directly."

Only report facts you saw in a tool result. Batch your searches into as few turns as possible. Call submit_business_profile once."""


def research_presence(business: str, location: str, website: str | None = None) -> dict:
    prompt = f"Business: {business}\nLocation: {location}"
    if website:
        prompt += f"\nWebsite: {website}"
    return run_agent(
        PRESENCE_SYSTEM, prompt, [search_web, read_pages, submit_business_profile],
        submit_business_profile, label="your business",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business")
    parser.add_argument("location")
    parser.add_argument("--sales", help="Square 'Items' sales export (CSV)")
    parser.add_argument("--website")
    args = parser.parse_args()
    out = {"presence": research_presence(args.business, args.location, args.website)}
    if args.sales:
        out["sales"] = analyze_sales(args.sales)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
