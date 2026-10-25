"""Fill the "Crumbs Hackathon" Supabase project for the Lovable app. Run on the laptop before the demo.

    cd backend
    .venv/bin/python scripts/sync_to_supabase.py --demo          # sample spots + alerts (no AI keys needed)
    .venv/bin/python scripts/sync_to_supabase.py                 # live: score, monitor, advise, Square alerts
    .venv/bin/python scripts/sync_to_supabase.py --skip-advisor  # same, without Ruth's slow advisor run

1. Scores the 5 food types for Capitol Hill (cached 24h; --refresh re-scores) → spots, spot_scores, top_rated alerts.
   --demo writes the made-up fixtures from backend/demo/ instead, flagged demo, when there are no AI keys.
2. For every business an owner created in the app (Ruth's businesses table): links it to a local crumbs business,
   scores it, and writes Home's Insights + Rivals → business_insights.
3. Runs Ruth's monitor for it (→ her changes table, plus owner and public alerts here) and her advisor
   (→ advisor_reports).
4. Square stock (Manny's logic, square_inventory.py) → low_stock (owner) and fresh_stock (public, opt-in) alerts.
   The token is single-merchant, so it's applied to one business: --square-business, or the only one there is.

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) in backend/.env; live parts also need
ANTHROPIC_API_KEY + TAVILY_API_KEY, the stock check SQUARE_ACCESS_TOKEN. Every key stays on this laptop.
Apply both files in supabase/migrations/ first.
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
            say(f"  {cuisine:6} {len(payload['spots'])} spots [{payload['source']}]")
        elif args.demo:
            store.publish_area(demo.spots(cuisine), demo=True)
            say(f"  {cuisine:6} sample spots (demo)")
        else:
            say(f"  {cuisine:6} skipped: no ANTHROPIC_API_KEY/TAVILY_API_KEY (add --demo for sample spots)")


def sync_demo_alerts() -> None:
    """backend/demo/alerts.json's public alerts, flagged demo, so the Alerts tab has something from Supabase."""
    now = datetime.now(timezone.utc)
    rows = [{**a, "spot_id": a["spotId"], "business_id": None, "demo": True,
             "created_at": (now - timedelta(minutes=a["minutesAgo"])).isoformat(timespec="seconds")}
            for a in demo._load("alerts.json")["alerts"] if a["audience"] == "consumer"]
    store.publish_alerts(rows)
    say(f"  {len(rows)} sample public alerts (demo)")


# ---------- 2-4. businesses ----------

def cuisine_of(row: dict) -> str | None:
    for value in (row.get("cuisine"), row.get("business_type")):
        text = (value or "").lower()
        for c in cuisines.CUISINES:
            if c["id"] in text or c["label"].lower() in text:
                return c["id"]
    return None


def link(row: dict, cuisine: str) -> dict:
    """The local crumbs business for one Supabase business, created or refreshed from the app's fields."""
    fields = {"name": row["name"], "address": row.get("address"), "lat": row.get("lat"), "lng": row.get("lng"),
              "business_type": cuisine, "share_stock_alerts": int(bool(row.get("share_stock_alerts"))),
              "low_stock_threshold": float(row.get("low_stock_threshold") or 5)}
    local = store.business_for_remote(row["id"])
    if local is None:
        business_id = store.create_business(name=row["name"], business_type=cuisine, location=row.get("location") or "Capitol Hill, Seattle",
                                            address=row.get("address"), lat=row.get("lat"), lng=row.get("lng"),
                                            website=row.get("website"))
        fields["supabase_business_id"] = row["id"]
    else:
        business_id = local["id"]
    store.update_business(business_id, **fields)
    store.set_goals(business_id, list(row.get("goals") or []))
    return store.get_business(business_id)


def change_alerts(local: dict, remote_id: str) -> int:
    """Ruth's changes for this business → an owner alert each, plus a public one for new spot / closed / price."""
    since = (datetime.now(timezone.utc) - timedelta(days=alerts.ALERT_DAYS)).isoformat(timespec="seconds")
    rows = []
    for change in store.remote_changes(remote_id, since):
        rows.append({**alerts.change_alert(change, "business", local["business_type"]), "business_id": remote_id})
        if change["kind"] in alerts.PUBLIC_CHANGES:
            public = alerts.change_alert(change, "consumer", local["business_type"])
            rows.append({**public, "id": f"chg-pub-{change['id']}", "business_id": None})
    store.publish_alerts(rows)
    return len(rows)


def run_advisor(remote_id: str, sales: str | None) -> str:
    agent_dir = str(config.REPO_ROOT / "agent")
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    import advisor  # Ruth's agent/advisor.py, saves to advisor_reports

    _, report_id = advisor.run_for_business(remote_id, sales)
    return report_id


def pick_square_business(remote: list[dict], wanted: str | None) -> str | None:
    if wanted:
        match = [r for r in remote if wanted in (r["id"], r["name"])]
        if not match:
            say(f"  --square-business {wanted!r} isn't in Supabase's businesses; skipping the stock check")
        return match[0]["id"] if match else None
    if len(remote) == 1:
        return remote[0]["id"]
    if remote:
        say("  Several businesses: pass --square-business <id or name> to choose which one Square stock belongs to")
    return None


def sync_businesses(args) -> None:
    remote = store.remote_businesses()
    if not remote:
        say("  No businesses yet. Owners create one from the app (Home → I run a spot); then run this again.")
        return
    square_id = pick_square_business(remote, args.square_business) if config.has_key("SQUARE_ACCESS_TOKEN") else None
    for row in remote:
        cuisine = cuisine_of(row)
        if not cuisine:
            say(f"  {row['name']}: skipped, its food type ({row.get('cuisine') or row.get('business_type')}) isn't one of the 5")
            continue
        local = link(row, cuisine)
        say(f"  {row['name']} ({cuisine})")
        if live_keys() and not args.skip_scores:
            pipeline.score_business(local["id"])  # never raises; the status says how it went
            local = store.get_business(local["id"])
            say(f"    scoring: {local['scoring_status']}{' (' + local['scoring_error'] + ')' if local['scoring_error'] else ''}")
        insights, rivals = pipeline.insights(local["id"]), pipeline.rivals(local["id"], 7)
        if insights and insights["breakdown"]:
            store.save_business_insights(row["id"], cuisine=cuisine, insights=insights, rivals=rivals)
            say(f"    insights: reputation {insights['reputation']}, momentum {insights['momentum']}, edge {insights['edge']}")
        else:
            say("    insights: not scored yet (the app shows sample insights until then)")
        if live_keys() and not args.skip_monitor:
            try:
                result = alerts.run_monitor(local["id"])
                say(f"    monitor: {'baseline saved' if result['baseline'] else str(result['changes']) + ' change(s)'}")
            except Exception as e:
                say(f"    monitor failed: {e}")
        say(f"    alerts from Ruth's changes: {change_alerts(local, row['id'])}")
        if config.has_key("ANTHROPIC_API_KEY") and not args.skip_advisor:
            try:
                sales = "square" if row["id"] == square_id else None
                say(f"    advisor: saved report {run_advisor(row['id'], sales)}")
            except Exception as e:
                say(f"    advisor failed: {e}")
        if row["id"] == square_id and not args.skip_stock:
            try:
                result = alerts.check_stock(local["id"])
                say(f"    Square: {result['items']} tracked item(s), {result['alertsAdded']} new alert(s)")
            except Exception as e:
                say(f"    Square stock check failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="write the sample spots and alerts (flagged demo) when there are no AI keys")
    parser.add_argument("--refresh", action="store_true", help="re-score food types even if a fresh result is cached")
    parser.add_argument("--square-business", metavar="ID_OR_NAME", help="which Supabase business the Square token belongs to")
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
        say("Check that both migrations in supabase/migrations/ are applied and the key is the service-role / secret key.")
        return 1
    say("\nDone. Open the Lovable app: it reads these tables with the anon key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
