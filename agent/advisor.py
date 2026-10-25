"""Tailored advice for one business: runs the competitor research and the
business analysis in parallel, then has Claude combine them into
recommendations specific to what this business lacks or could change.

Usage:
    python agent/advisor.py "Test Bakery" bakery "Capitol Hill, Seattle" --sales data/sample_sales.csv
    python agent/advisor.py "My Cafe" cafe "Ballard, Seattle" --sales square
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

import business_agent
import competitor_agent
import fast_competitors
import notify
import pos
from agent_loop import MODEL


class Recommendation(BaseModel):
    title: str = Field(description="Short imperative, e.g. 'Bake a second batch of cardamom buns'")
    category: Literal["pricing", "menu", "hours", "marketing", "operations", "service"]
    action: str = Field(description="Exactly what to do, concrete enough to act on this week")
    evidence_from_your_business: str = Field(description="What the owner's own sales or reviews show; 'none' if not applicable")
    evidence_from_market: str = Field(description="What competitors or customers in the area show; 'none' if not applicable")
    est_monthly_impact_usd: float | None = Field(description="Conservative extra monthly revenue; null if it can't be grounded in the data")
    impact_math: str = Field(description="The arithmetic behind the estimate, with each assumption labeled")
    confidence: Literal["high", "medium", "low"]


class AdvisorReport(BaseModel):
    snapshot: str = Field(description="2-4 sentences on how this business is doing and where it stands against the local market")
    strengths: list[str] = Field(description="What the business does well that it should keep, with evidence")
    gaps_vs_competitors: list[str] = Field(description="What nearby competitors offer or do that this business doesn't, or does worse")
    recommendations: list[Recommendation] = Field(description="4-6 recommendations, highest estimated impact first")
    caveats: list[str] = Field(description="Limits of the data behind these recommendations")


ADVISOR_SYSTEM = """You advise the owner of a small, brick-and-mortar business. You get three inputs: an analysis of their own sales data, what customers say about them online, and research on nearby competitors. Turn them into recommendations tailored to this specific business.

- Every recommendation must connect the owner's own data to the market: e.g. "your almond croissant is $5.50; 4 nearby shops charge $6.00-$6.75" or "your cardamom bun sells out by 8:30am every day; no competitor sells one". Don't repeat generic competitor advice that ignores what this business already does.
- Look for: items priced below the local range, items that sell out (lost sales), slow sellers taking up oven time, days or hours when competitors are closed and this business is too, things competitors are praised or criticized for, and gaps in the owner's online presence.
- Dollar estimates must be conservative and use only numbers in the inputs (units per day, prices, open days per month). Show the math and label assumptions, e.g. "assume 10% fewer units after a price increase". If a recommendation can't be grounded in numbers (e.g. a new opening day), you may estimate from the owner's average revenue per day with a clearly labeled discount, or leave the estimate null. Never present an estimate as certain.
- Remember sales data only shows what sold, not what customers wanted: a sold-out item's true demand is unknown, so size estimates for it cautiously.
- Not finding something online (e.g. a Google listing) is not evidence that it doesn't exist. Recommend checking it, not creating it, unless the research positively shows it's missing.
- The sales data may be a sample; treat it as the owner's real data.
- If <own_sales_analysis> says no sales data was provided, base the advice on the competitor research and the online presence only: leave est_monthly_impact_usd null and say in impact_math that there is no sales data to size it, and mention in the caveats that sales data would sharpen the advice."""

NO_SALES = {"items": [], "note": "No sales data was provided."}


def load_sales(source: str | None, days: int) -> dict:
    """`source` is "square", "toast", the path to a sales CSV export, or None for no sales data."""
    if source is None:
        return NO_SALES
    if source == "square":
        return business_agent.analyze_rows(pos.fetch_square(days))
    if source == "toast":
        return business_agent.analyze_rows(pos.fetch_toast(days))
    return business_agent.analyze_sales(source)


def run(
    business: str, business_type: str, location: str, sales_source: str | None,
    website: str | None = None, days: int = 56, fast: bool = False,
) -> dict:
    start = time.monotonic()
    # --fast: parallel per-competitor research and a faster model for the advice (see fast_competitors.py).
    model = os.environ.get("ADVISOR_MODEL", "claude-sonnet-5-5") if fast else MODEL
    research = fast_competitors.run if fast else competitor_agent.run
    with ThreadPoolExecutor(max_workers=3) as pool:
        if fast:  # sales analysis is near-instant for a CSV, so do it first and price-check the owner's top sellers
            sales = load_sales(sales_source, days)
            top_items = [i["item"] for i in sales["items"][:4]]
            competitors_f = pool.submit(research, business, business_type, location, top_items)
            sales_f = None
        else:
            competitors_f = pool.submit(research, business, business_type, location)
        presence_f = pool.submit(business_agent.research_presence, business, location, website, fast_competitors.FAST_MODEL if fast else None)
        if not fast:
            sales_f = pool.submit(load_sales, sales_source, days)
        presence = presence_f.result()
        if sales_f is not None:
            sales = sales_f.result()
        competitors = competitors_f.result()
    print(f"[advisor] research done in {time.monotonic() - start:.0f}s, writing advice...", file=sys.stderr)

    t0 = time.monotonic()
    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        system=ADVISOR_SYSTEM,
        output_config={"effort": "medium"},
        output_format=AdvisorReport,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": (
                f"Business: {business} ({business_type}), {location}\n\n"
                f"<own_sales_analysis>\n{json.dumps(sales, indent=1)}\n</own_sales_analysis>\n\n"
                f"<own_online_presence>\n{json.dumps(presence, indent=1)}\n</own_online_presence>\n\n"
                f"<competitor_research>\n{json.dumps(competitors, indent=1)}\n</competitor_research>"
            ),
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Advisor request was declined: {response.stop_details}")
    if response.parsed_output is None:
        raise RuntimeError(f"Advisor returned no report (stop_reason={response.stop_reason})")
    print(f"[advisor] advice written in {time.monotonic() - t0:.0f}s, total {time.monotonic() - start:.0f}s", file=sys.stderr)

    return {
        "business": business,
        "type": business_type,
        "location": location,
        "date": date.today().isoformat(),
        "advice": response.parsed_output.model_dump(),
        "your_sales": sales,
        "your_online_presence": presence,
        "competitors": competitors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business", help="Business name")
    parser.add_argument("business_type", help="e.g. bakery, dog groomer, cafe")
    parser.add_argument("location", help="Neighborhood and city, e.g. 'Ballard, Seattle'")
    parser.add_argument(
        "--sales",
        help="'square' or 'toast' to pull from the POS API (credentials in .env), or a path to a sales CSV export. Optional: without it the advice rests on the competitor research alone",
    )
    parser.add_argument("--days", type=int, default=56, help="Days of POS sales to pull (default 56)")
    parser.add_argument("--website", help="The business's website, if it has one")
    parser.add_argument("--email", metavar="ADDRESS", help="Email the finished report to this address (SMTP settings in .env, see README)")
    parser.add_argument("--email-preview", action="store_true", help="With --email: write an HTML preview to reports/ instead of sending")
    parser.add_argument("--fast", action="store_true", help="Much faster: parallel per-competitor research and a faster model")
    args = parser.parse_args()

    report = run(args.business, args.business_type, args.location, args.sales, args.website, args.days, args.fast)

    competitor_agent.REPORTS_DIR.mkdir(exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in args.business.lower()).strip("-")
    out = competitor_agent.REPORTS_DIR / f"{slug}-{report['date']}-advisor.json"
    out.write_text(json.dumps(report, indent=2))

    advice = report["advice"]
    print(f"\n{advice['snapshot']}\n")
    for r in advice["recommendations"]:
        impact = f"~${r['est_monthly_impact_usd']:,.0f}/mo" if r["est_monthly_impact_usd"] else "impact n/a"
        print(f"- [{r['category']}] {r['title']} ({impact}, {r['confidence']} confidence)")
    print(f"\nSaved to {out}")

    if args.email:  # the report is already saved, so an email problem never loses it
        try:
            print(notify.email_report(report, args.email, competitor_agent.REPORTS_DIR if args.email_preview else None))
        except Exception as e:
            print(f"Could not email the report: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
