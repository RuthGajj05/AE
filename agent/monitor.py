"""Competitor monitoring: re-check a business's competitors and notify the owner
of meaningful changes (a new shop nearby, a price change, a closure...).

The first run saves a baseline. Each later run re-researches the same tracked
competitors, compares with the last snapshot and, if anything material
changed, sends the owner a short message.

Local mode (snapshots in state/<business>/, gitignored):
    python agent/monitor.py "Sea Wolf Bakers" bakery "Fremont, Seattle" [--sms +12065550123]

Supabase mode (businesses, snapshots and notifications in Supabase):
    python agent/monitor.py --all               # check every business with monitoring on
    python agent/monitor.py --business-id UUID  # check one business
    python agent/monitor.py --deliver           # send texts/emails that are due

Run --all on a schedule (e.g. Mon/Wed/Fri) and --deliver hourly, so texts go
out at each owner's chosen hour.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

import anthropic
import httpx
from pydantic import BaseModel, Field

import competitor_agent
import fast_competitors
from agent_loop import MODEL
from supabase_store import SupabaseStore

STATE_DIR = Path(__file__).resolve().parent.parent / "state"


class Change(BaseModel):
    kind: Literal[
        "new_competitor", "closed", "price_change", "hours_change", "rating_change", "review_trend", "other"
    ]
    competitor: str
    before: str = Field(description="The value in the previous snapshot; 'none' for a new competitor")
    after: str = Field(description="The value in the new snapshot")
    evidence: str = Field(description="Source or detail from the new snapshot that shows the change is real")
    why_it_matters: str = Field(description="One sentence on what it means for the owner")


class ChangeReport(BaseModel):
    changes: list[Change] = Field(description="Only material, well-supported changes; empty if none")
    message: str = Field(
        description="Text message to the owner (under 600 characters) covering the most important changes "
        "and one suggested action; empty string if there are no changes"
    )


DIFF_SYSTEM = """You compare two snapshots of research on a small business's local competitors, taken a few days apart, and decide what the owner should be told.

Report a change only when it is real and comparable:
- Both snapshots must contain the fact for the same competitor (e.g. a croissant price in both). A price, rating or hours value that is missing from either snapshot is not a change.
- Ignore differences in wording, item naming ("Butter croissant" vs "Croissant, butter"), ordering, sources used, and small rating moves (under 0.2 stars) or review-count growth that is just normal accumulation.
- A competitor present in only one snapshot counts as new or closed only if its status field (or other evidence in the new snapshot) says it opened, is opening, or closed. Otherwise it was just researched differently; ignore it.
- A price is a change only if the same item at the same shop has a different price; note the direction and amount.
When unsure, leave it out: a false alert costs the owner's trust more than a missed one.

Write the message for a busy owner reading a text: plain words, most important change first, concrete numbers, and one practical suggestion. No greeting fluff."""


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def tracked_competitors(snapshot: dict) -> list[dict]:
    """The previous snapshot's competitors still worth re-checking (closed ones are dropped)."""
    return [c for c in snapshot["competitors"]
            if not (c.get("status") or "").lower().startswith(("permanently closed", "closed"))]


def tracked_from(snapshot: dict) -> list[str]:
    tracked = []
    for c in snapshot["competitors"]:
        if (c.get("status") or "").lower().startswith(("permanently closed", "closed")):
            continue
        tracked.append(f"{c['name']}, {c['address']}" if c.get("address") else c["name"])
    return tracked


def diff(previous: dict, current: dict) -> ChangeReport:
    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=8000,
        system=DIFF_SYSTEM,
        output_config={"effort": "medium"},
        output_format=ChangeReport,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": (
                f"Owner's business: {current['business']} ({current['type']}), {current['location']}\n\n"
                f"<previous_snapshot date=\"{previous['date']}\">\n{json.dumps(previous['competitors'], indent=1)}\n</previous_snapshot>\n\n"
                f"<new_snapshot date=\"{current['date']}\">\n{json.dumps(current['competitors'], indent=1)}\n</new_snapshot>"
            ),
        }],
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"Diff failed (stop_reason={response.stop_reason})")
    return response.parsed_output


# ---------- Sending ----------

def send_sms(to: str, message: str) -> None:
    sid, token, sender = (os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"))
    if not (sid and token and sender):
        raise RuntimeError("Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM in .env")
    httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token), data={"From": sender, "To": to, "Body": message}, timeout=30,
    ).raise_for_status()


def send_email(to: str, subject: str, message: str) -> None:
    key, sender = os.environ.get("RESEND_API_KEY"), os.environ.get("RESEND_FROM")
    if not (key and sender):
        raise RuntimeError("Set RESEND_API_KEY and RESEND_FROM in .env")
    httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {key}"},
        json={"from": sender, "to": [to], "subject": subject, "text": message},
        timeout=30,
    ).raise_for_status()


# ---------- Local file storage ----------

class FileStore:
    """Keeps snapshots and a notifications log in state/<business>/. Texts send immediately."""

    def __init__(self, sms_to: str | None = None):
        self.sms_to = sms_to

    def _folder(self, business: dict) -> Path:
        return STATE_DIR / _slug(business["name"])

    def start_run(self, business: dict) -> None:
        return None

    def finish_run(self, run_id, *, error=None, changes=0, baseline=False) -> None:
        pass

    def latest_snapshot(self, business: dict) -> dict | None:
        snaps = sorted(self._folder(business).glob("*.json"))
        return json.loads(snaps[-1].read_text()) if snaps else None

    def save_snapshot(self, business: dict, data: dict, run_id) -> str:
        folder = self._folder(business)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now().strftime('%Y-%m-%dT%H%M%S')}.json"
        path.write_text(json.dumps(data, indent=2))
        return str(path)

    def save_changes(self, business, changes, run_id, snapshot_id, previous_snapshot_id) -> None:
        pass  # the changes are in the notification and the snapshots

    def queue_notifications(self, business: dict, title: str, message: str, run_id) -> None:
        print(f"\n=== {title} ===\n{message}\n")
        with (self._folder(business) / "notifications.log").open("a") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {title}\n{message}\n\n")
        if self.sms_to:
            try:
                send_sms(self.sms_to, message)
                print(f"SMS sent to {self.sms_to}", file=sys.stderr)
            except Exception as e:
                print(f"SMS not sent: {e}", file=sys.stderr)


# ---------- The check ----------

def check(business: dict, store) -> ChangeReport | None:
    """Re-research one business's competitors, save the snapshot, and notify on changes.
    `business` needs name, business_type and location (plus id and preferences for Supabase)."""
    name = business["name"]
    run_id = store.start_run(business)
    try:
        previous = store.latest_snapshot(business)
        # Both runs use the per-competitor research (prices, hours, ratings for each shop), so snapshots compare
        # like for like; re-checks follow the same shops and re-price the items found last time.
        if previous is None:
            current = fast_competitors.run(name, business["business_type"], business["location"])
        else:
            current = fast_competitors.run_tracked(name, business["business_type"], business["location"],
                                                   tracked_competitors(previous))
        snapshot_id = store.save_snapshot(business, current, run_id)

        if previous is None:
            print(f"[{name}] baseline saved ({snapshot_id}); the next run will compare against it", file=sys.stderr)
            store.finish_run(run_id, baseline=True)
            return None

        report = diff(previous, current)
        print(f"[{name}] {len(report.changes)} change(s) since {previous['date']}", file=sys.stderr)
        for c in report.changes:
            print(f"  - [{c.kind}] {c.competitor}: {c.before} -> {c.after}", file=sys.stderr)
        store.save_changes(
            business, [c.model_dump() for c in report.changes], run_id, snapshot_id, previous.get("_id"),
        )
        if report.changes and report.message:
            title = f"{len(report.changes)} change(s) near {name}"
            store.queue_notifications(business, title, report.message, run_id)
        store.finish_run(run_id, changes=len(report.changes))
        return report
    except Exception as e:
        store.finish_run(run_id, error=str(e))
        raise


def deliver_due(store) -> None:
    """Send the texts and emails whose send time has come (Supabase mode)."""
    due = store.due_notifications()
    print(f"{len(due)} notification(s) due", file=sys.stderr)
    for n in due:
        b = n.get("businesses") or {}
        try:
            if n["channel"] == "sms":
                if not (b.get("sms_opt_in") and b.get("sms_phone")):
                    store.mark_notification(n["id"], "skipped", "SMS opt-in or phone missing")
                    continue
                send_sms(b["sms_phone"], n["message"])
            elif n["channel"] == "email":
                if not (b.get("email_opt_in") and b.get("email")):
                    store.mark_notification(n["id"], "skipped", "Email opt-in or address missing")
                    continue
                send_email(b["email"], n.get("title") or f"Update for {b.get('name')}", n["message"])
            store.mark_notification(n["id"], "sent")
        except Exception as e:
            store.mark_notification(n["id"], "failed", str(e))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business", nargs="?")
    parser.add_argument("business_type", nargs="?")
    parser.add_argument("location", nargs="?")
    parser.add_argument("--sms", help="Local mode: owner's phone number to text, e.g. +12065550123")
    parser.add_argument("--all", action="store_true", help="Supabase: check every business with monitoring on")
    parser.add_argument("--business-id", help="Supabase: check one business by id")
    parser.add_argument("--deliver", action="store_true", help="Supabase: send texts/emails that are due")
    args = parser.parse_args()

    if args.all or args.business_id or args.deliver:
        store = SupabaseStore()
        if args.all or args.business_id:
            businesses = [store.get_business(args.business_id)] if args.business_id else store.monitored_businesses()
            failures = 0
            for b in businesses:
                try:
                    check(b, store)
                except Exception as e:
                    failures += 1
                    print(f"[{b['name']}] failed: {e}", file=sys.stderr)
            print(f"Checked {len(businesses)} business(es), {failures} failed", file=sys.stderr)
        deliver_due(store)
    elif args.business and args.business_type and args.location:
        business = {"name": args.business, "business_type": args.business_type, "location": args.location}
        check(business, FileStore(args.sms))
    else:
        parser.error("give a business, type and location, or use --all / --business-id / --deliver")


if __name__ == "__main__":
    main()
