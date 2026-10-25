"""Ruth's monitor for app businesses: runs in SQLite even when Supabase is configured, turns changes into owner
alerts, and emails the owner. Research, the diff and email sending are faked: no network calls."""

import pytest

import alerts
import store
from tests.test_api import client  # noqa: F401  (pytest fixture)


class FakeNotify:
    sent = []
    configured = True

    @classmethod
    def email_configured(cls):
        return cls.configured

    @staticmethod
    def validate_recipient(address):
        return address

    @classmethod
    def send_email(cls, msg):
        cls.sent.append(msg)


@pytest.fixture()
def monitored(client, monkeypatch):
    monkeypatch.setattr(alerts, "supabase_configured", lambda: True)  # configured, but app businesses aren't linked

    def no_supabase():
        raise AssertionError("an unlinked business must not touch Supabase")

    monkeypatch.setattr(alerts, "_supabase", no_supabase)
    monkeypatch.setattr(alerts.emails, "_notify", lambda: FakeNotify)
    FakeNotify.sent, FakeNotify.configured = [], True

    monitor = alerts._monitor_module()
    snapshots = iter([
        {"business": "Crumb & Co", "type": "Bakery", "location": "x", "date": "2026-10-20",
         "competitors": [{"name": "Byen Bakeri", "address": "15 Nickerson St"}]},
        {"business": "Crumb & Co", "type": "Bakery", "location": "x", "date": "2026-10-25",
         "competitors": [{"name": "Byen Bakeri", "address": "15 Nickerson St"}]},
    ])
    monkeypatch.setattr(monitor.fast_competitors, "run", lambda *a, **k: next(snapshots))
    monkeypatch.setattr(monitor.fast_competitors, "run_tracked", lambda *a, **k: next(snapshots))
    monkeypatch.setattr(monitor, "diff", lambda prev, cur: monitor.ChangeReport(changes=[
        monitor.Change(kind="price_change", competitor="Byen Bakeri", before="Croissant $4.85", after="Croissant $5.25",
                       evidence="own menu", why_it_matters="Your $4.00 croissant is now $1.25 under them."),
    ], message="Byen Bakeri raised its croissant to $5.25 (was $4.85). You're $1.25 under them."))

    business_id = store.create_business(name="Crumb & Co", business_type="bakery", location="Fremont, Seattle",
                                        address="3617 Stone Way N, Seattle, WA", lat=47.6508, lng=-122.3428)
    store.update_business(business_id, kind="Bakery", owner_email="owner@example.com")
    return client, business_id


def test_changes_become_owner_alerts_and_an_email(monitored):
    client, business_id = monitored
    assert alerts.run_monitor(business_id) == {"baseline": True, "changes": 0}
    assert FakeNotify.sent == []  # a baseline has nothing to report
    assert alerts.run_monitor(business_id) == {"baseline": False, "changes": 1}

    [msg] = FakeNotify.sent
    assert msg["To"] == "owner@example.com" and msg["Subject"] == "1 change(s) near Crumb & Co"
    assert "Byen Bakeri raised its croissant to $5.25" in msg.get_body(("plain",)).get_content()
    assert "<script" not in msg.get_body(("html",)).get_content()

    owner = client.get("/api/alerts", params={"audience": "business", "businessId": business_id}).json()
    assert [a["kind"] for a in owner] == ["price_change"]
    settings = client.get(f"/api/business/{business_id}/settings").json()
    assert settings["emailAlerts"] is True and settings["recentEmails"][0]["status"] == "sent"


@pytest.mark.parametrize("setup, reason", [
    (lambda bid: store.update_business(bid, email_alerts=0), "turned alert emails off"),
    (lambda bid: store.update_business(bid, owner_email=None), "No owner email"),
    (lambda bid: setattr(FakeNotify, "configured", False), "isn't set up on the server"),
])
def test_skipped_emails_say_why(monitored, setup, reason):
    client, business_id = monitored
    setup(business_id)
    alerts.run_monitor(business_id)
    alerts.run_monitor(business_id)
    assert FakeNotify.sent == []
    [entry] = store.email_log(business_id)
    assert entry["status"] == "skipped" and reason in entry["detail"]
    assert client.get("/api/alerts", params={"audience": "business", "businessId": business_id}).json()  # alert kept


def test_a_failed_send_is_logged_not_raised(monitored, monkeypatch):
    client, business_id = monitored

    def broken(msg):
        raise RuntimeError("Resend 401")

    monkeypatch.setattr(FakeNotify, "send_email", staticmethod(broken))
    alerts.run_monitor(business_id)
    assert alerts.run_monitor(business_id)["changes"] == 1
    [entry] = store.email_log(business_id)
    assert entry["status"] == "failed" and "Resend 401" in entry["detail"]


def test_owner_can_turn_alert_emails_off(monitored):
    client, business_id = monitored
    off = client.post(f"/api/business/{business_id}/settings", json={"emailAlerts": False}).json()
    assert off["emailAlerts"] is False and store.get_business(business_id)["email_alerts"] == 0


def test_onboarding_records_the_owner_email(monkeypatch):
    import auth
    import pipeline
    from fastapi.testclient import TestClient

    import main
    monkeypatch.setattr(auth, "enabled", lambda: True)
    monkeypatch.setattr(auth, "user_from_token", lambda t: {"id": "u1", "email": "maker@example.com"})
    monkeypatch.setattr(pipeline, "score_business", lambda *a: None)
    with TestClient(main.app) as c:
        r = c.post("/api/business/onboard", headers={"Authorization": "Bearer t"}, json={
            "name": "Crumb & Co", "address": "1 Pike St", "lat": 47.6195, "lng": -122.3205,
            "businessType": "Bakery", "advisorReport": False})
    assert store.get_business(r.json()["businessId"])["owner_email"] == "maker@example.com"
