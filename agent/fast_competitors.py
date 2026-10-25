"""Faster competitor research.

Same output as competitor_agent.run, but built for speed:
  1. Discovery: OpenStreetMap and one web search run at the same time, then one short
     call picks the competitors worth researching.
  2. Research: every competitor gets its own small agent, all running in parallel, each
     writing only its own entry (instead of one agent writing every competitor's entry
     in one long final answer, which was ~half of the old run time).

The per-competitor agents use a faster model (FAST_MODEL env var, default
claude-sonnet-5-5) at low effort. Facts only, same rules as the original agent.

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

if __package__:
    from . import competitor_agent as base
    from .agent_loop import run_agent
    from .evidence_store import normalized
    from .market_intelligence import EvidenceBundle, MenuObservation
else:
    import competitor_agent as base
    from agent_loop import run_agent
    from evidence_store import normalized
    from market_intelligence import EvidenceBundle, MenuObservation

FAST_MODEL = os.environ.get("FAST_MODEL", "claude-sonnet-5-5")  # claude-haiku-5-5 is faster still but less careful (it once took a delivery-app rating for the shop's own)
PICK_MODEL = os.environ.get("PICK_MODEL", "claude-sonnet-5-5")  # short call, so a stronger model costs only a few seconds
MAX_COMPETITORS = int(os.environ.get("MAX_COMPETITORS", "8"))


class Pick(BaseModel):
    name: str
    address: str | None = Field(None, description="Street address, to find this exact branch")
    website: str | None = None


class Picks(BaseModel):
    competitors: list[Pick]


class MenuItem(BaseModel):
    product: str = Field(description="Item name exactly as written on the page")
    category: str = Field(description="Plain generic name, lowercase, e.g. 'almond croissant' for 'Twice-Baked Almond Croissant'")
    price: str | None = Field(None, description="Price as listed, e.g. '$4.75'")
    source_url: str = Field(description="The read_pages URL where the item appears")


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
    menu_items: list[MenuItem] | None = None,
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
        menu_items: Every product listed on a menu page you read with read_pages (up to 40), verbatim, each with a generic category.
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
Keep every field short: price_points like 'Croissant: $4.75', praised_for and complaints as short phrases.

menu_items: list the products on any menu page you read with read_pages (up to 40), with the name exactly as written there and that page's URL.
Only items from pages you read: not from search snippets, delivery apps you didn't read, or memory. Items that aren't on the page get discarded.
Give each a category: the plain generic name a customer would use, lowercase, without brand names or adjectives
('Twice-Baked Almond Croissant' -> 'almond croissant', 'Sea Salt Choc Chip' -> 'chocolate chip cookie', 'Pain au Chocolat' -> 'chocolate croissant').
If an item is the same kind of product as one of the owner's items listed below, use the owner's item name (lowercase) as the category."""


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


def _research_one(pick: Pick, business_type: str, location: str, items: list[str],
                  owner_products: list[str]) -> dict:
    prompt = f"Competitor: {pick.name}\nAddress: {pick.address or 'unknown'}\nWebsite: {pick.website or 'unknown'}\nType: {business_type}\nArea: {location}"
    if items:
        prompt += f"\nFind prices for these items first (the owner sells them; use the closest equivalent on this menu): {', '.join(items)}"
    if owner_products:
        prompt += f"\nOwner's items (for menu_items categories): {', '.join(owner_products)}"
    # A session per competitor records exactly which pages this agent read, so its
    # menu items can be checked against them (the same check the source specialists use).
    with base.research_session() as session:
        result = run_agent(
            ONE_SYSTEM, prompt, [base.search_web, base.read_pages, submit_competitor], submit_competitor,
            label=pick.name[:14], model=FAST_MODEL, effort="low", max_turns=6,
        )
        result["_menu_observations"], result["_menu_dropped"] = _verified_menu(result, pick, session.ledger)
    return result


def _verified_menu(result: dict, pick: Pick, ledger) -> tuple[list[dict], int]:
    """Keep menu items that appear verbatim on a page this agent read; drop the rest."""
    items = result.pop("menu_items", None) or []
    name, address = result.get("name") or pick.name, result.get("address") or pick.address
    if not address:
        return [], len(items)  # branch identity needs an address
    kept, dropped = [], 0
    for item in items:
        try:
            observation = MenuObservation(
                business_name=name, address=address, source_url=item["source_url"],
                product=item["product"], category=item.get("category"), price=item.get("price"),
                observed_at=date.today(),
            )
            ledger.validate(EvidenceBundle(menu_observations=[observation]), {(normalized(name), normalized(address))})
            kept.append(observation.model_dump(mode="json"))
        except (ValueError, KeyError, TypeError):
            dropped += 1
    return kept, dropped


def run(business: str, business_type: str, location: str, items: list[str] | None = None,
        owner_products: list[str] | None = None) -> dict:
    """`items` are the owner's best sellers: every competitor is asked for the price of those.
    `owner_products` (all of the owner's items) lets menu items be categorized under the owner's names."""
    start = time.monotonic()
    items = items or []
    owner_products = owner_products or []
    osm, web = _discover(business_type, location)
    print(f"[fast] discovery {time.monotonic() - start:.0f}s", file=sys.stderr)
    picks = _pick(business, business_type, location, osm, web)
    print(f"[fast] picked {len(picks)} competitors at {time.monotonic() - start:.0f}s", file=sys.stderr)

    def safe(p: Pick) -> dict | None:
        try:
            return _research_one(p, business_type, location, items, owner_products)
        except Exception as e:  # one bad competitor must not sink the whole run
            print(f"[fast] {p.name}: failed ({e})", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=len(picks) or 1) as pool:
        results = [r for r in pool.map(safe, picks) if r]
    menu = [m for r in results for m in r.pop("_menu_observations", [])]
    dropped = sum(r.pop("_menu_dropped", 0) for r in results)
    print(f"[fast] done in {time.monotonic() - start:.0f}s; {len(menu)} menu items kept, {dropped} dropped", file=sys.stderr)

    return {
        "business": business,
        "type": business_type,
        "location": location,
        "date": date.today().isoformat(),
        # Menu items are checked against the pages each agent read; no review
        # observations are collected, so review trends stay empty.
        "mode": "live_research",
        "collector": "fast",
        "competitors": [
            {k: (v if v is not None or k in ("address", "website", "rating", "review_count", "hours") else []) for k, v in r.items() if k != "caveats"}
            for r in results
        ],
        "gaps_and_caveats": [f"{r.get('name')}: {c}" for r in results for c in (r.get("caveats") or [])]
        + ([f"{dropped} menu item(s) were dropped: not found verbatim on a page the agent read, or the shop had no address."] if dropped else []),
        "evidence_bundle": EvidenceBundle(menu_observations=menu).model_dump(mode="json"),
    }


# ---------- repeat checks for the monitor ----------

class StatusNote(BaseModel):
    name: str
    address: str | None = None
    status: str = Field(description="e.g. 'Opened Oct 2026 (Eater Seattle)', 'Permanently closed (Yelp)'")
    source: str = Field(description="URL that says so")


@beta_tool
def submit_openings(changes: list[StatusNote], notes: list[str] | None = None) -> str:
    """Submit businesses that recently opened, are opening soon, or closed. Call exactly once; an empty list is fine.

    Args:
        changes: One entry per business with a dated source for the opening or closure.
        notes: Anything you couldn't verify.
    """
    return "Received."


OPENINGS_SYSTEM = """You check whether businesses of a given type near a location recently opened, are about to open,
or closed (within about the last three months). Run one batch of searches, e.g. "new <type> <location>",
"<type> opening <location>", "<type> closed <location>". Report a business only when a source with a date says it
opened, is opening, or closed; put that in status with the month and the source name. Never guess. Then call
submit_openings once (an empty list is fine)."""


def _openings(business_type: str, location: str, tracked: list[str]) -> list[dict]:
    prompt = f"Type: {business_type}\nLocation: {location}\nAlready tracked: {', '.join(tracked) or 'none'}"
    try:
        result = run_agent(OPENINGS_SYSTEM, prompt, [base.search_web, submit_openings], submit_openings,
                           label="openings", model=FAST_MODEL, effort="low", max_turns=4)
    except Exception as e:  # openings are a bonus: the price/hours re-check still counts
        print(f"[fast] openings check failed ({e})", file=sys.stderr)
        return []
    return [c for c in result.get("changes") or [] if c.get("name") and c.get("status")]


def run_tracked(business: str, business_type: str, location: str, tracked: list[dict]) -> dict:
    """Re-check the same competitors as last time, for the monitor: one agent per tracked competitor (re-pricing the
    items found last time, so prices compare like for like) plus one search for openings and closures nearby.
    `tracked` is the previous snapshot's competitor entries."""
    start = time.monotonic()
    picks = [Pick(name=c["name"], address=c.get("address"), website=c.get("website")) for c in tracked if c.get("name")]
    items = list(dict.fromkeys(
        p.split(":")[0].strip() for c in tracked for p in (c.get("price_points") or []) if ":" in p
    ))[:8]

    def safe(p: Pick) -> dict | None:
        try:
            return _research_one(p, business_type, location, items, [])
        except Exception as e:
            print(f"[fast] {p.name}: failed ({e})", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=(len(picks) or 1) + 1) as pool:
        openings_f = pool.submit(_openings, business_type, location, [p.name for p in picks])
        results = [r for r in pool.map(safe, picks) if r]
        openings = openings_f.result()

    menu = [m for r in results for m in r.pop("_menu_observations", [])]
    for r in results:
        r.pop("_menu_dropped", 0)
    competitors = [
        {k: (v if v is not None or k in ("address", "website", "rating", "review_count", "hours") else []) for k, v in r.items() if k != "caveats"}
        for r in results
    ]
    by_name = {normalized(c["name"]): c for c in competitors}
    for note in openings:
        known = by_name.get(normalized(note["name"]))
        if known is not None:
            known["status"] = note["status"]
            known.setdefault("sources", []).append(note["source"])
        else:
            competitors.append({"name": note["name"], "address": note.get("address"), "status": note["status"],
                                "sources": [note["source"]], "price_points": [], "praised_for": [], "complaints": [],
                                "specialties": []})
    print(f"[fast] re-check done in {time.monotonic() - start:.0f}s; {len(openings)} opening/closure note(s)", file=sys.stderr)
    return {
        "business": business, "type": business_type, "location": location, "date": date.today().isoformat(),
        "mode": "live_research", "collector": "fast_tracked", "competitors": competitors,
        "gaps_and_caveats": [f"{r.get('name')}: {c}" for r in results for c in (r.get("caveats") or [])],
        "evidence_bundle": EvidenceBundle(menu_observations=menu).model_dump(mode="json"),
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
