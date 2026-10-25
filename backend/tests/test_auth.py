"""Business endpoints need a signed-in owner (Supabase Auth); browsing and demo data don't. Token checks are faked:
no network calls."""

import pytest

import auth
import demo
import reports
import store
from tests.test_api import FakeAdvisor, client, live  # noqa: F401  (pytest fixtures)

USERS = {"token-ana": {"id": "user-ana", "email": "ana@example.com"},
         "token-ben": {"id": "user-ben", "email": "ben@example.com"}}


@pytest.fixture()
def signed(live, monkeypatch):
    monkeypatch.setattr(auth, "enabled", lambda: True)
    monkeypatch.setattr(auth, "user_from_token", lambda token: USERS.get(token))
    monkeypatch.setattr(reports.alerts, "supabase_configured", lambda: False)
    return live


def as_user(token):
    return {"Authorization": f"Bearer {token}"}


def onboard(client, token):
    return client.post("/api/business/onboard", headers=as_user(token) if token else {}, json={
        "name": "Kaito Sushi", "address": "100 Broadway E, Seattle, WA", "lat": 47.6195, "lng": -122.3205, "cuisine": "sushi"})


def test_onboarding_needs_a_sign_in_and_records_the_owner(signed):
    r = onboard(signed, None)
    assert r.status_code == 401 and "sign in" in r.json()["error"]
    assert onboard(signed, "token-wrong").status_code == 401

    business_id = onboard(signed, "token-ana").json()["businessId"]
    assert store.get_business(business_id)["owner_user_id"] == "user-ana"

    me = signed.get("/api/me", headers=as_user("token-ana")).json()
    assert me["user"]["email"] == "ana@example.com" and me["business"]["id"] == business_id
    assert signed.get("/api/me", headers=as_user("token-ben")).json()["business"] is None
    assert signed.get("/api/me").status_code == 401


def test_only_the_owner_sees_the_business(signed):
    business_id = onboard(signed, "token-ana").json()["businessId"]
    paths = [f"/api/business/{business_id}/report", f"/api/business/{business_id}/insights",
             f"/api/business/{business_id}/rivals"]
    for path in paths:
        assert signed.get(path, headers=as_user("token-ana")).status_code == 200, path
        assert signed.get(path, headers=as_user("token-ben")).status_code == 404, path  # same as missing
        assert signed.get(path).status_code == 401, path
    assert signed.post(f"/api/business/{business_id}/report", headers=as_user("token-ben")).status_code == 404
    assert signed.post(f"/api/business/{business_id}/report", headers=as_user("token-ana")).status_code == 202

    owner_alerts = {"audience": "business", "businessId": business_id}
    assert signed.get("/api/alerts", params=owner_alerts, headers=as_user("token-ana")).status_code == 200
    assert signed.get("/api/alerts", params=owner_alerts, headers=as_user("token-ben")).status_code == 404


def test_browsing_and_demo_data_stay_open(signed):
    assert signed.get("/api/cuisines").status_code == 200
    assert signed.get("/api/alerts", params={"audience": "consumer", "lat": 47.62, "lng": -122.32}).status_code == 200
    assert signed.get("/api/business/x/report", params={"demo": "true"}).json()["status"] == "complete"
    assert signed.get(f"/api/business/{demo.BUSINESS_ID}/insights").status_code == 200
    assert signed.get("/api/alerts", params={"audience": "business", "businessId": demo.BUSINESS_ID}).status_code == 200


def test_with_auth_off_nothing_is_gated(live, monkeypatch):
    monkeypatch.setattr(auth, "enabled", lambda: False)
    monkeypatch.setattr(reports.alerts, "supabase_configured", lambda: False)
    business_id = onboard(live, None).json()["businessId"]
    assert live.get(f"/api/business/{business_id}/report").status_code == 200
