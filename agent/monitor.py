"""Competitor monitoring: re-check a business's competitors and notify the owner
of meaningful changes (a new shop nearby, a price change, a closure...).

The first run saves a baseline. Each later run re-researches the same tracked
competitors, compares with the last snapshot and, if anything material
changed, sends the owner a short message.

Usage:
    python agent/monitor.py "Sea Wolf Bakers" bakery "Fremont, Seattle" [--sms +12065550123]

Run it on a schedule (e.g. cron, Mon/Wed/Fri) to keep the owner updated.
Snapshots are kept in state/<business>/ (gitignored).
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
from agent_loop import MODEL

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


def latest_snapshot(business: str) -> dict | None:
    snaps = sorted((STATE_DIR / _slug(business)).glob("*.json"))
    return json.loads(snaps[-1].read_text()) if snaps else None


def save_snapshot(business: str, snapshot: dict) -> Path:
    folder = STATE_DIR / _slug(business)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now().strftime('%Y-%m-%dT%H%M%S')}.json"
    path.write_text(json.dumps(snapshot, indent=2))
    return path


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


def notify(business: str, message: str, sms_to: str | None) -> None:
    """Print and log the message, and text it if Twilio is configured."""
    print(f"\n=== Message for {business} ===\n{message}\n")
    log = STATE_DIR / _slug(business) / "notifications.log"
    with log.open("a") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}]\n{message}\n\n")

    sid, token, sender = (os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"))
    if not sms_to:
        return
    if not (sid and token and sender):
        print("SMS not sent: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM in .env", file=sys.stderr)
        return
    resp = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={"From": sender, "To": sms_to, "Body": message},
        timeout=30,
    )
    resp.raise_for_status()
    print(f"SMS sent to {sms_to}", file=sys.stderr)


def check(business: str, business_type: str, location: str, sms_to: str | None = None) -> ChangeReport | None:
    previous = latest_snapshot(business)
    tracked = tracked_from(previous) if previous else None
    current = competitor_agent.run(business, business_type, location, tracked=tracked)
    path = save_snapshot(business, current)

    if previous is None:
        print(f"Baseline saved to {path}. The next run will compare against it.", file=sys.stderr)
        return None

    report = diff(previous, current)
    print(f"{len(report.changes)} change(s) since {previous['date']}. Snapshot saved to {path}", file=sys.stderr)
    for c in report.changes:
        print(f"- [{c.kind}] {c.competitor}: {c.before} -> {c.after}", file=sys.stderr)
    if report.changes and report.message:
        notify(business, report.message, sms_to)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business")
    parser.add_argument("business_type")
    parser.add_argument("location")
    parser.add_argument("--sms", help="Owner's phone number to text, e.g. +12065550123 (needs Twilio keys in .env)")
    args = parser.parse_args()
    check(args.business, args.business_type, args.location, args.sms)


if __name__ == "__main__":
    main()
