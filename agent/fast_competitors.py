"""Faster competitor research.

Same output as competitor_agent.run, but built for speed:
  1. Discovery: OpenStreetMap and one web search run at the same time, then one short
     call picks the competitors worth researching.
  2. Research: every competitor gets its own small agent, all running in parallel, each
     writing only its own entry (instead of one agent writing every competitor's entry
     in one long final answer, which was ~half of the old run time).

The per-competitor agents use a smaller, faster model (FAST_MODEL env var, default
claude-haiku-5-5) at low effort. Facts only, same rules as the original agent.

Usage:
    python agent/fast_competitors.py "Test Bakery" bakery "Capitol Hill, Seattle"
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import anthropic
from anthropic import beta_tool
from pydantic import BaseModel, Field

import competitor_agent as base
from agent_loop import run_agent

FAST_MODEL = os.environ.get("FAST_MODEL", "claude-sonnet-5-5")  # claude-haiku-5-5 is faster still but less careful (it once took a delivery-app rating for the shop's own)
PICK_MODEL = os.environ.get("PICK_MODEL", "claude-sonnet-5-5")  # short call, so a stronger model costs only a few seconds
MAX_COMPETITORS = int(os.environ.get("MAX_COMPETITORS", "8"))


class Pick(BaseModel):
    name: str
    address: str | None = Field(None, description="Street address, to find this exact branch")
    website: str | None = None


class Picks(BaseModel):
    competitors: list[Pick]


@beta_tool
def submit_competitor(
    name: str,
    address: str | None = None,
    website: str | None = None,
    rating: float | None = None,
    review_count: int | None = None,
    hours: str | None = None,
    price_points: list[str] | None = None,
    praised_for: list[str] | None = None,
    complaints: list[str] | None = None,
    specialties: list[str] | None = None,
    sources: list[str] | None = None,
    caveats: list[str] | None = None,
) -> str:
    """Submit your findings for this one competitor. Call exactly once. Leave a field empty/null if it was not found.

    Args:
        name: Business name.
        address: Street address of this exact branch.
        website: Its website.
        rating: Average star rating, if found.
        review_count: Number of reviews, if found.
        hours: e.g. 'We-Su 7am-5pm, closed Mon-Tue'.
        price_points: Item and price, e.g. 'Croissant: $4.75'.
        praised_for: Recurring positives in reviews, as short phrases.
        complaints: Recurring negatives in reviews, as short phrases.
        specialties: What it is known for.
        sources: Up to 3 URLs this entry is mainly based on.
        caveats: Short notes on what you could not verify (missing prices, rating may belong to another branch).
    """
    return "Received."


PICK_SYSTEM = f"""You choose which nearby businesses to research as competitors of a small brick-and-mortar business.
You get OpenStreetMap results and web search results. Choose up to {MAX_COMPETITORS} direct competitors (same kind of business),
balancing the closest ones with the best-known ones. Closeness matters most: customers choose among shops in their own neighborhood,
so prefer businesses in the OpenStreetMap list (sorted nearest first) and well-known shops in the same neighborhood; only go farther out if there are too few nearby.
Skip the business itself, unrelated branches of chains, and anything a source says has closed.
Only use names and addresses that appear in the input; leave address empty if not given."""

ONE_SYSTEM = """You research ONE competitor of a small, brick-and-mortar business and report facts only.

Work in at most two rounds of tool calls, batching every call of a round into the same turn:
Round 1 (all at once): search_web purpose="reviews" for "<name> <street address> reviews" (include the address so you get this exact branch);
search_web for "<name> menu prices"; and read_pages on its website if it has one.
Round 2 (only if needed): one batch to fill obvious gaps (e.g. a price search for the 2-3 core items).
Then call submit_competitor once.

Rules: only report what you saw in a tool result, list up to 3 source URLs, never estimate a price or rating, and leave a field empty (and say why in caveats) if it wasn't found.
Yelp and TripAdvisor pages can't be read with read_pages, only their search snippets. If a rating may belong to another branch, say so in caveats.
Keep every field short: price_points like 'Croissant: $4.75', praised_for and complaints as short phrases."""


def _discover(business_type: str, location: str) -> tuple[str, str]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        osm = pool.submit(base.find_nearby_osm.call, {"location": location, "place_types": [business_type]})
        web = pool.submit(base.search_web.call, {"query": f"best {business_type} in {location}", "purpose": "discovery"})
        return osm.result(), web.result()


def _pick(business: str, business_type: str, location: str, osm: str, web: str) -> list[Pick]:
    resp = anthropic.Anthropic().messages.parse(
        model=PICK_MODEL,
        max_tokens=4000,
        system=PICK_SYSTEM,
        output_config={"effort": "low"},
        output_format=Picks,
        messages=[{"role": "user", "content": f"Business: {business} ({business_type}), {location}\n\n<openstreetmap>\n{osm}\n</openstreetmap>\n\n<web_search>\n{web}\n</web_search>"}],
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"Competitor selection returned nothing (stop_reason={resp.stop_reason})")
    return resp.parsed_output.competitors[:MAX_COMPETITORS]


def _research_one(pick: Pick, business_type: str, location: str, items: list[str]) -> dict:
    prompt = f"Competitor: {pick.name}\nAddress: {pick.address or 'unknown'}\nWebsite: {pick.website or 'unknown'}\nType: {business_type}\nArea: {location}"
    if items:
        prompt += f"\nFind prices for these items first (the owner sells them; use the closest equivalent on this menu): {', '.join(items)}"
    return run_agent(
        ONE_SYSTEM, prompt, [base.search_web, base.read_pages, submit_competitor], submit_competitor,
        label=pick.name[:14], model=FAST_MODEL, effort="low", max_turns=6,
    )


def run(business: str, business_type: str, location: str, items: list[str] | None = None) -> dict:
    """`items` are the owner's best sellers: every competitor is asked for the price of those."""
    start = time.monotonic()
    items = items or []
    osm, web = _discover(business_type, location)
    print(f"[fast] discovery {time.monotonic() - start:.0f}s", file=sys.stderr)
    picks = _pick(business, business_type, location, osm, web)
    print(f"[fast] picked {len(picks)} competitors at {time.monotonic() - start:.0f}s", file=sys.stderr)

    def safe(p: Pick) -> dict | None:
        try:
            return _research_one(p, business_type, location, items)
        except Exception as e:  # one bad competitor must not sink the whole run
            print(f"[fast] {p.name}: failed ({e})", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=len(picks) or 1) as pool:
        results = [r for r in pool.map(safe, picks) if r]
    print(f"[fast] done in {time.monotonic() - start:.0f}s", file=sys.stderr)

    return {
        "business": business,
        "type": business_type,
        "location": location,
        "date": date.today().isoformat(),
        "competitors": [
            {k: (v if v is not None or k in ("address", "website", "rating", "review_count", "hours") else []) for k, v in r.items() if k != "caveats"}
            for r in results
        ],
        "gaps_and_caveats": [f"{r.get('name')}: {c}" for r in results for c in (r.get("caveats") or [])],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business")
    parser.add_argument("business_type")
    parser.add_argument("location")
    args = parser.parse_args()
    report = run(args.business, args.business_type, args.location)
    base.REPORTS_DIR.mkdir(exist_ok=True)
    out = base.REPORTS_DIR / f"fast-{date.today().isoformat()}.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nSaved {len(report['competitors'])} competitors to {out}")


if __name__ == "__main__":
    main()
