"""Advisor reports (Ruth's advisor) through the backend: onboarding queues one, the endpoints show its status,
summary and full JSON. The advisor itself is faked: no network calls."""

from datetime import datetime, timedelta, timezone

import pytest

import alerts
import reports
import store
from tests.test_api import FakeAdvisor, live  # noqa: F401  (pytest fixture)


def onboard(client, **extra):
    r = client.post("/api/business/onboard", json={
        "name": "Kaito Sushi", "address": "100 Broadway E, Seattle, WA", "lat": 47.6195, "lng": -122.3205,
        "cuisine": "sushi", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_onboarding_queues_a_report_and_the_app_can_read_it(live, monkeypatch):
    monkeypatch.setattr(reports.alerts, "supabase_configured", lambda: False)
    FakeAdvisor.calls.clear()
    body = onboard(live)
    assert body["reportQueued"] is True

    args, kwargs = FakeAdvisor.calls[-1]
    assert args[:3] == ("Kaito Sushi", "sushi restaurant", store.get_business(body["businessId"])["location"])
    assert args[3] is None  # no Square connected: advice from competitor research alone

    view = live.get(f"/api/business/{body['businessId']}/report").json()
    assert view["status"] == "complete" and view["error"] is None and view["demo"] is False
    s = view["summary"]
    assert s["recommendations"] and {"title", "action", "monthlyImpactUsd", "confidence"} <= s["recommendations"][0].keys()
    assert s["competitors"] and s["snapshot"]
    assert view["report"]["advice"]["recommendations"]  # the full report rides along for the dashboard


def test_onboarding_can_skip_the_report(live):
    body = onboard(live, advisorReport=False)
    assert body["reportQueued"] is False
    assert live.get(f"/api/business/{body['businessId']}/report").json()["status"] == "none"


def test_refresh_runs_a_new_report_and_keeps_showing_the_last_one_while_it_runs(live, monkeypatch):
    business_id = onboard(live, advisorReport=False)["businessId"]
    assert live.post(f"/api/business/{business_id}/report").json()["status"] == "running"
    first = live.get(f"/api/business/{business_id}/report").json()
    assert first["status"] == "complete"

    # A second request while one is running joins it instead of starting another.
    running_id = store.start_report(business_id)
    again = live.post(f"/api/business/{business_id}/report").json()
    assert again["reportId"] == running_id
    view = live.get(f"/api/business/{business_id}/report").json()
    assert view["status"] == "running" and view["summary"] is not None  # last complete report still shown


def test_a_failed_report_is_explained_and_the_last_good_one_kept(live, monkeypatch):
    business_id = onboard(live)["businessId"]

    class Broken:
        @staticmethod
        def run(*a, **k):
            raise RuntimeError("Tavily 500")

    monkeypatch.setattr(reports, "_advisor", lambda: Broken)
    live.post(f"/api/business/{business_id}/report")
    view = live.get(f"/api/business/{business_id}/report").json()
    assert view["status"] == "failed" and "Tavily 500" in view["error"]
    assert view["summary"] is not None  # the onboarding report is still there


def test_an_abandoned_running_report_shows_as_failed(live):
    business_id = onboard(live, advisorReport=False)["businessId"]
    report_id = store.start_report(business_id)
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    with store._db() as db:
        db.execute("update advisor_reports set created_at = ? where id = ?", (old, report_id))
    view = live.get(f"/api/business/{business_id}/report").json()
    assert view["status"] == "failed" and "stopped" in view["error"]


def test_report_is_copied_to_supabase_when_the_business_is_linked(live, monkeypatch):
    saved = {}

    class FakeSupabase:
        def get_business(self, sid):
            return {"id": sid}

        def save_advisor_report(self, business, report):
            saved["business"] = business["id"]
            return "sb-report-1"

    monkeypatch.setattr(alerts, "supabase_configured", lambda: True)
    monkeypatch.setattr(alerts, "_supabase", FakeSupabase)
    business_id = onboard(live, advisorReport=False)["businessId"]
    store.update_business(business_id, supabase_business_id="sb-biz-1")
    live.post(f"/api/business/{business_id}/report")
    assert saved == {"business": "sb-biz-1"}
    assert store.latest_report(business_id)["supabase_report_id"] == "sb-report-1"


def test_demo_report_and_errors(client):
    demo = client.get("/api/business/anything/report", params={"demo": "true"}).json()
    assert demo["status"] == "complete" and demo["demo"] is True and demo["summary"]["recommendations"]
    assert client.get("/api/business/nope/report").status_code == 404
    assert client.post("/api/business/nope/report").status_code == 404


@pytest.fixture()
def client(monkeypatch):
    from tests.test_api import client as base  # same setup: no keys, throwaway database
    yield from base.__wrapped__(monkeypatch)
