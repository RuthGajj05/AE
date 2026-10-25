"""Scheduled competitor checks: which slot applies, which businesses are due, and that a tick checks only those."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import scheduler
import store

SEA = ZoneInfo("America/Los_Angeles")
MWF = scheduler.parse_schedule("mon,wed,fri@08:00")


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=SEA)


def test_schedule_parsing():
    assert MWF == ({0, 2, 4}, scheduler.time(8, 0))
    assert scheduler.parse_schedule("off") is None
    with pytest.raises(ValueError):
        scheduler.parse_schedule("someday@08:00")


@pytest.mark.parametrize("now, slot", [
    (at(2026, 10, 26, 8, 0), at(2026, 10, 26, 8, 0)),   # Monday 8:00 exactly
    (at(2026, 10, 26, 7, 59), at(2026, 10, 23, 8, 0)),  # Monday before 8 → Friday's slot
    (at(2026, 10, 27, 15, 0), at(2026, 10, 26, 8, 0)),  # Tuesday → Monday's slot
    (at(2026, 10, 25, 12, 0), at(2026, 10, 23, 8, 0)),  # Sunday → Friday's slot
])
def test_latest_slot(now, slot):
    assert scheduler.latest_slot(now, *MWF) == slot


@pytest.fixture()
def businesses(monkeypatch):
    monkeypatch.setenv("ALERT_SCHEDULE", "mon,wed,fri@08:00")
    for key in ("ANTHROPIC_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.setenv(key, "test")
    with store._db() as db:
        db.execute("delete from businesses")
    store.init()
    fresh = store.create_business(name="Checked Monday", business_type="bakery", location="Fremont, Seattle")
    stale = store.create_business(name="Checked Friday", business_type="bakery", location="Fremont, Seattle")
    never = store.create_business(name="Never checked", business_type="bakery", location="Fremont, Seattle")
    store.create_business(name="Demo", business_type="sushi", location="x", demo=True)
    for business_id, when in ((fresh, at(2026, 10, 26, 8, 5)), (stale, at(2026, 10, 23, 8, 5))):
        run_id = store.start_monitor_run(business_id)
        with store._db() as db:
            db.execute("update monitor_runs set started_at = ? where id = ?", (when.isoformat(timespec="seconds"), run_id))
    ran = []
    import alerts
    monkeypatch.setattr(alerts, "run_monitor", lambda bid: ran.append(bid) or {"baseline": False, "changes": 0})
    return {"fresh": fresh, "stale": stale, "never": never, "ran": ran}


def test_a_tick_checks_only_businesses_not_checked_since_the_last_slot(businesses):
    checked = scheduler.run_due(now=at(2026, 10, 27, 10, 0))  # Tuesday: last slot is Monday 8:00
    assert set(checked) == {businesses["stale"], businesses["never"]}  # not the demo, not the one done Monday
    assert set(businesses["ran"]) == set(checked)


def test_a_missed_slot_is_caught_up_and_not_repeated(businesses):
    scheduler.run_due(now=at(2026, 10, 28, 13, 0))  # Wednesday afternoon, laptop was asleep at 8
    assert len(businesses["ran"]) == 3
    for business_id in businesses["ran"]:  # what the real monitor would have recorded
        store.start_monitor_run(business_id)
    businesses["ran"].clear()
    assert scheduler.run_due(now=datetime.now(SEA) + timedelta(minutes=1)) == []  # restart a minute later: nothing


def test_off_and_missing_keys_do_nothing(businesses, monkeypatch):
    monkeypatch.setenv("ALERT_SCHEDULE", "off")
    assert scheduler.run_due(now=at(2026, 10, 28, 9, 0)) == []
    monkeypatch.setenv("ALERT_SCHEDULE", "mon,wed,fri@08:00")
    monkeypatch.delenv("TAVILY_API_KEY")
    assert scheduler.run_due(now=at(2026, 10, 28, 9, 0)) == []
