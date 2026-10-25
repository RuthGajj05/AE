"""Scheduled competitor checks for app businesses, inside the backend while it runs.

Every few minutes: for each business (not the demo), if its last monitor run started before the most recent
scheduled slot (default Mon/Wed/Fri 08:00 Seattle time), run Ruth's monitor for it now. Changes become owner
alerts and an email (alerts.run_monitor). Because it compares against the latest slot, a check missed while the
backend was off or the laptop asleep runs as soon as it's back, and restarts never check twice. A newly onboarded
business has no runs yet, so it gets its baseline within one tick.

ALERT_SCHEDULE: "mon,wed,fri@08:00" (default) or "off". ALERT_TIMEZONE: default America/Los_Angeles.
On a server, scripts/check_alerts.py on a cron does the same job; turn this off there.
"""

import os
import sys
import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import config
import store

TICK_SECONDS = 600
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_started = False


def parse_schedule(text: str) -> tuple[set[int], time] | None:
    """("mon,wed,fri@08:00") → ({0, 2, 4}, 08:00); None for "off"."""
    text = (text or "").strip().lower()
    if text in ("", "off", "none", "0"):
        return None
    days_part, _, at = text.partition("@")
    days = {DAYS[d.strip()[:3]] for d in days_part.split(",") if d.strip()[:3] in DAYS}
    hour, _, minute = (at or "08:00").partition(":")
    if not days:
        raise ValueError(f"ALERT_SCHEDULE has no valid days: {text!r}")
    return days, time(int(hour), int(minute or 0))


def latest_slot(now: datetime, days: set[int], at: time) -> datetime:
    """The most recent scheduled time at or before `now` (an aware datetime in the schedule's time zone)."""
    for back in range(8):
        day = (now - timedelta(days=back)).date()
        slot = datetime.combine(day, at, tzinfo=now.tzinfo)
        if day.weekday() in days and slot <= now:
            return slot
    raise AssertionError("a schedule with at least one day always has a slot in the last week")


def due(slot: datetime) -> list[dict]:
    """Businesses whose last monitor run started before `slot` (or that have never run)."""
    out = []
    for b in store.list_businesses():
        last = store.last_monitor_run(b["id"])
        if last is None or datetime.fromisoformat(last["started_at"]) < slot:
            out.append(b)
    return out


def run_due(now: datetime | None = None) -> list[str]:
    """One tick: check every business that's due. Returns their ids. Never raises."""
    schedule = parse_schedule(os.environ.get("ALERT_SCHEDULE", "mon,wed,fri@08:00"))
    if schedule is None:
        return []
    import alerts
    import pipeline
    if not all(config.has_key(k) for k in pipeline.LIVE_KEYS):
        return []
    tz = ZoneInfo(os.environ.get("ALERT_TIMEZONE", "America/Los_Angeles"))
    now = (now or datetime.now(tz)).astimezone(tz)
    checked = []
    for b in due(latest_slot(now, *schedule)):
        try:
            result = alerts.run_monitor(b["id"])
            print(f"[scheduler] {b['name']}: {'baseline' if result['baseline'] else str(result['changes']) + ' change(s)'}",
                  file=sys.stderr)
        except Exception as e:  # one business failing must not stop the rest
            print(f"[scheduler] {b['name']}: failed ({str(e)[:200]})", file=sys.stderr)
        checked.append(b["id"])
    return checked


def start() -> bool:
    """Start the background thread once (from the app's startup). False when scheduling is off."""
    global _started
    schedule_text = os.environ.get("ALERT_SCHEDULE", "mon,wed,fri@08:00")
    if _started or config.demo_mode() or parse_schedule(schedule_text) is None:
        return False
    _started = True

    def loop():
        first = True
        while True:
            threading.Event().wait(30 if first else TICK_SECONDS)  # a short first wait lets the server start
            first = False
            run_due()

    threading.Thread(target=loop, name="alert-scheduler", daemon=True).start()
    print(f"[scheduler] competitor checks on: {schedule_text} ({os.environ.get('ALERT_TIMEZONE', 'America/Los_Angeles')})",
          file=sys.stderr)
    return True
