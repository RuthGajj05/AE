"""Fill the Lovable app's Supabase tables. Run on the laptop before the demo.

    cd backend
    .venv/bin/python scripts/sync_to_supabase.py --demo          # sample spots + alerts (no AI keys needed)
    .venv/bin/python scripts/sync_to_supabase.py                 # live: score, monitor, advise, Square alerts
    .venv/bin/python scripts/sync_to_supabase.py --skip-advisor  # same, without Ruth's slow advisor run

Writes Lovable's tables in their exact shapes (the app owns them; this never changes them):
  spots        one row per spot: id, name, cuisine, letter (A–D), lat, lng, address, price, distance_mi, hours, phone
  spot_scores  one row per spot and attribute: spot_id, attribute, score, wait_minutes, ambiance_pct,
               ambiance_mention_rate ("1 of 4 reviews"), best_at, reason, is_pick
  alerts       id (uuid), kind, audience, spot_id, title, detail, distance_mi, created_at
  picks        only read (the app adds them; Home's momentum and rivals count them)
  profiles     only read: account_type = 'business' rows are the businesses to monitor

1. Scores the 5 food types for Capitol Hill (cached 24h; --refresh re-scores) → spots, spot_scores, top_rated alerts.
   --demo writes the made-up fixtures from backend/demo/ instead when there are no AI keys.
2. For each business account: scores it, then (if Ruth's migration is applied in this project) runs her monitor and
   advisor through her businesses table and turns her changes into alerts.
3. Square stock (Manny's logic, square_inventory.py) → low_stock (owner) and fresh_stock (public, opt-in) alerts.
   The token is single-merchant, so it's applied to one business: --square-business, or the only one there is.
   Public fresh-stock alerts are opt-in: pass --share-stock-alerts only if the owner agreed (Lovable's profiles
   table has no setting for it). Low-stock alerts (with counts) always go to the owner's audience.

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) in backend/.env; live parts also need
ANTHROPIC_API_KEY + TAVILY_API_KEY, the stock check SQUARE_ACCESS_TOKEN. Every key stays on this laptop.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import alerts  # noqa: E402
import config  # noqa: E402  (loads backend/.env)
import cuisines  # noqa: E402
import demo  # noqa: E402
import pipeline  # noqa: E402
import store  # noqa: E402
import supabase_rest  # noqa: E402


def say(msg: str) -> None:
    print(msg, flush=True)


def live_keys() -> bool:
    return all(config.has_key(k) for k in pipeline.LIVE_KEYS)


# ---------- 1. spots ----------

def sync_spots(args) -> None:
    hill = config.CAPITOL_HILL
    for c in cuisines.CUISINES:
        cuisine = c["id"]
        if live_keys():
            try:
                payload = pipeline.get_spots(cuisine, hill["lat"], hill["lng"], hill["radiusMi"], refresh=args.refresh)
            except Exception as e:
                say(f"  {cuisine:6} scoring failed: {e}")
                continue
            store.publish_area(payload)  # a cached result wasn't sent when it was scored, so send it now
            say(f"  {cuisine:6} {min(4, len(payload['spots']))} spots [{payload['source']}]")
        elif args.demo:
            store.publish_area(demo.spots(cuisine), demo=True)
            say(f"  {cuisine:6} 4 sample spots (demo)")
        else:
            say(f"  {cuisine:6} skipped: no ANTHROPIC_API_KEY/TAVILY_API_KEY (add --demo for sample spots)")


def sync_demo_alerts() -> None:
    """backend/demo/alerts.json's public alerts, so the Alerts tab has something to show."""
    now = datetime.now(timezone.utc)
    rows = [{**a, "spot_id": a["spotId"], "created_at": (now - timedelta(minutes=a["minutesAgo"])).isoformat(timespec="seconds")}
            for a in demo._load("alerts.json")["alerts"] if a["audience"] == "consumer"]
    store.publish_alerts(rows)
    say(f"  {len(rows)} sample public alerts (demo)")


# ---------- 2-3. businesses ----------

def cuisine_of(profile: dict) -> str | None:
    text = (profile.get("cuisine") or "").lower()
    return next((c["id"] for c in cuisines.CUISINES if c["id"] in text or c["label"].lower() in text), None)


def link(profile: dict, cuisine: str, ruth_id: str | None) -> dict:
    """The local crumbs business for one business account, created or refreshed from its profile."""
    profile_key = f"profile:{profile['user_id']}"
    local = (store.business_for_remote(ruth_id) if ruth_id else None) or store.business_for_remote(profile_key)
    name = profile.get("business_name") or profile.get("display_name") or "My spot"
    address = profile.get("business_address")
    if local is None:
        business_id = store.create_business(name=name, business_type=cuisine, location=config.CAPITOL_HILL["label"], address=address)
    else:
        business_id = local["id"]
    # Ruth's monitor needs her businesses.id; without her tables the profile is the link.
    store.update_business(business_id, name=name, address=address, business_type=cuisine, supabase_business_id=ruth_id or profile_key)
    return store.get_business(business_id)


def change_alerts(local: dict, ruth_id: str) -> int:
    """Ruth's changes for this business → an owner alert each, plus a public one for new spot / closed / price."""
    since = (datetime.now(timezone.utc) - timedelta(days=alerts.ALERT_DAYS)).isoformat(timespec="seconds")
    rows = []
    for change in store.remote_changes(ruth_id, since):
        rows.append(alerts.change_alert(change, "business", local["business_type"]))
        if change["kind"] in alerts.PUBLIC_CHANGES:
            rows.append({**alerts.change_alert(change, "consumer", local["business_type"]), "id": f"chg-pub-{change['id']}"})
    store.publish_alerts(rows)
    return len(rows)


def run_advisor(ruth_id: str, sales: str | None) -> str:
    agent_dir = str(config.REPO_ROOT / "agent")
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    import advisor  # Ruth's agent/advisor.py, saves to her advisor_reports table

    _, report_id = advisor.run_for_business(ruth_id, sales)
    return report_id


def pick_square_business(profiles: list[dict], wanted: str | None) -> str | None:
    if wanted:
        match = [p for p in profiles if wanted in (p["user_id"], p.get("business_name"))]
        if not match:
            say(f"  --square-business {wanted!r} isn't a business account in profiles; skipping the stock check")
        return match[0]["user_id"] if match else None
    if len(profiles) == 1:
        return profiles[0]["user_id"]
    if profiles:
        say("  Several business accounts: pass --square-business <business name or user id> for the Square stock check")
    return None


def sync_businesses(args) -> None:
    profiles = store.remote_businesses()
    if not profiles:
        say("  No business accounts yet (profiles.account_type = 'business'). Create one in the app, then run this again.")
        return
    square_owner = pick_square_business(profiles, args.square_business) if config.has_key("SQUARE_ACCESS_TOKEN") else None
    for profile in profiles:
        name = profile.get("business_name") or profile.get("display_name") or profile["user_id"]
        cuisine = cuisine_of(profile)
        if not cuisine:
            say(f"  {name}: skipped, its food type ({profile.get('cuisine')}) isn't one of the 5")
            continue
        ruth_id = store.ruth_business(profile, cuisine)
        local = link(profile, cuisine, ruth_id)
        say(f"  {name} ({cuisine})")
        if live_keys() and not args.skip_scores:
            pipeline.score_business(local["id"])  # never raises; the status says how it went
            local = store.get_business(local["id"])
            say(f"    scoring: {local['scoring_status']}{' (' + local['scoring_error'] + ')' if local['scoring_error'] else ''}")
        insights = pipeline.insights(local["id"])
        if insights and insights["breakdown"]:
            # Lovable has no table for these yet; printed so you can see them.
            say(f"    insights: reputation {insights['reputation']}, momentum {insights['momentum']}, edge {insights['edge']}")
        if ruth_id is None:
            say("    monitor + advisor: skipped (Ruth's migration isn't applied in this Supabase project)")
        else:
            if live_keys() and not args.skip_monitor:
                try:
                    result = alerts.run_monitor(local["id"])
                    say(f"    monitor: {'baseline saved' if result['baseline'] else str(result['changes']) + ' change(s)'}")
                except Exception as e:
                    say(f"    monitor failed: {e}")
            say(f"    alerts from Ruth's changes: {change_alerts(local, ruth_id)}")
            if config.has_key("ANTHROPIC_API_KEY") and not args.skip_advisor:
                try:
                    sales = "square" if profile["user_id"] == square_owner else None
                    say(f"    advisor: saved report {run_advisor(ruth_id, sales)}")
                except Exception as e:
                    say(f"    advisor failed: {e}")
        if profile["user_id"] == square_owner and not args.skip_stock:
            if args.share_stock_alerts:
                store.update_business(local["id"], share_stock_alerts=1)
            try:
                result = alerts.check_stock(local["id"])
                say(f"    Square: {result['items']} tracked item(s), {result['alertsAdded']} new alert(s)")
            except Exception as e:
                say(f"    Square stock check failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="write the sample spots and alerts when there are no AI keys")
    parser.add_argument("--refresh", action="store_true", help="re-score food types even if a fresh result is cached")
    parser.add_argument("--square-business", metavar="NAME_OR_USER_ID", help="which business account the Square token belongs to")
    parser.add_argument("--share-stock-alerts", action="store_true",
                        help="the Square business agreed to public 'fresh in' alerts (never with counts)")
    parser.add_argument("--skip-scores", action="store_true", help="don't score food types or businesses")
    parser.add_argument("--skip-monitor", action="store_true", help="don't run Ruth's competitor monitor")
    parser.add_argument("--skip-advisor", action="store_true", help="don't run Ruth's advisor (the slowest step)")
    parser.add_argument("--skip-stock", action="store_true", help="don't check Square stock")
    args = parser.parse_args()

    if not supabase_rest.configured():
        say("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) in backend/.env first.")
        return 1
    store.init()
    say(f"Supabase: {supabase_rest.url()}")
    if not args.skip_scores:
        say("Food types (Capitol Hill):")
        sync_spots(args)
    if args.demo:
        say("Alerts:")
        sync_demo_alerts()
    say("Businesses:")
    sync_businesses(args)

    if supabase_rest.errors:
        say(f"\n{len(supabase_rest.errors)} Supabase write(s) failed. First one: {supabase_rest.errors[0]}")
        say("Check the key is the service-role / secret key and the Lovable tables exist.")
        return 1
    say("\nDone. The Lovable app reads these tables.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
