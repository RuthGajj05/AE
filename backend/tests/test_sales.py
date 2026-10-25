"""Optional sales connections (CSV, Square, Toast) and free-text business types. POS calls and the advisor are
faked: no network calls."""

import sqlite3

import pytest

import config
import cuisines
import pipeline
import reports
import sales
import store
from tests.test_api import FakeAdvisor, client, live  # noqa: F401  (pytest fixtures)

SAMPLE = (config.REPO_ROOT / "data" / "sample_sales.csv").read_text()
OWN_CSV = "Date,Time,Item,Qty,Gross Sales\n2026-10-01,08:10:00,Croissant,2,$9.00\n2026-10-02,09:00:00,Latte,1,$5.50\n"


@pytest.fixture()
def owner(live, monkeypatch, tmp_path):
    monkeypatch.setattr(reports.alerts, "supabase_configured", lambda: False)
    monkeypatch.setattr(sales, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(sales, "KEY_FILE", tmp_path / "key")
    monkeypatch.delenv("SALES_CREDENTIALS_KEY", raising=False)
    FakeAdvisor.calls.clear()
    return live


def onboard(client, **body):
    r = client.post("/api/business/onboard", json={"name": "Crumb & Co", "address": "1 Pike St, Seattle",
                                                  "lat": 47.6195, "lng": -122.3205, **body})  # no live geocoding
    assert r.status_code == 200, r.text
    return r.json()["businessId"]


def last_sales_passed():
    return FakeAdvisor.calls[-1][1]["sales"]


def test_free_text_types_match_crumbs_food_types():
    assert cuisines.match("Sushi bar") == "sushi" and cuisines.match("pizzeria") == "pizza"
    assert cuisines.match("Taqueria") == "tacos" and cuisines.match("bakery") is None and cuisines.match("Café") is None
    assert cuisines.research_type({"kind": "Bakery", "business_type": "bakery"}) == "Bakery"
    assert cuisines.research_type({"kind": None, "business_type": "sushi"}) == "sushi restaurant"


def test_a_bakery_onboards_without_crumbs_scoring(owner, monkeypatch):
    scored = []
    monkeypatch.setattr(pipeline, "score_business", lambda *a: scored.append(a))
    business_id = onboard(owner, businessType="Bakery")
    b = store.get_business(business_id)
    assert (b["business_type"], b["kind"], b["scoring_status"]) == ("bakery", "Bakery", "unsupported")
    assert scored == []  # crumbs' review scoring is for its food types only
    assert FakeAdvisor.calls[-1][0][1] == "Bakery"  # the report researches it in the owner's words
    assert owner.get(f"/api/business/{business_id}/insights").json()["status"] == "unsupported"
    assert owner.get(f"/api/business/{business_id}/rivals").json()["status"] == "unsupported"


def test_a_described_food_type_still_gets_crumbs_scoring(owner):
    business_id = onboard(owner, businessType="Sushi bar")
    b = store.get_business(business_id)
    assert (b["business_type"], b["kind"]) == ("sushi", "Sushi bar")
    assert onboard(owner, cuisine="ramen") and owner.post("/api/business/onboard", json={"name": "X"}).status_code == 400


def test_csv_upload_is_checked_used_by_reports_and_sample_data_stays_labeled(owner):
    business_id = onboard(owner, businessType="Bakery", advisorReport=False)
    bad = owner.post(f"/api/business/{business_id}/sales/csv", json={"filename": "x.csv", "content": "a,b\n1,2\n"})
    assert bad.status_code == 400 and "Date, Time, Item, Qty and Gross Sales" in bad.json()["error"]

    r = owner.post(f"/api/business/{business_id}/sales/csv", json={"filename": "oct.csv", "content": OWN_CSV}).json()
    assert r["connected"] and r["source"] == "csv" and r["label"] == "oct.csv" and r["items"] == 2 and r["sample"] is False
    assert r["reportStarted"] is True
    used = last_sales_passed()
    assert used["total_revenue"] == 14.5 and used["is_synthetic"] is False

    owner.post(f"/api/business/{business_id}/sales/csv", json={"filename": "sample.csv", "content": SAMPLE})
    assert last_sales_passed()["is_synthetic"] is True  # the repo's fake sample is never presented as real


def test_square_token_is_checked_encrypted_and_never_returned(owner, monkeypatch):
    business_id = onboard(owner, businessType="Cafe", advisorReport=False)
    pos = sales._agent()[1]
    monkeypatch.setattr(pos, "check_square", lambda token, env: [{"id": "L1", "name": "Pike St"}] if token == "sq-good-token" else 1 / 0)
    fetched = {}
    monkeypatch.setattr(pos, "fetch_square", lambda days, **kw: fetched.update(kw) or
                        [{"Date": "2026-10-01", "Time": "08:00:00", "Item": "Latte", "Qty": 1, "Gross Sales": 5.5}])

    bad = owner.post(f"/api/business/{business_id}/sales/square", json={"accessToken": "sq-bad-token-x"})
    assert bad.status_code == 400 and "didn't accept" in bad.json()["error"]

    r = owner.post(f"/api/business/{business_id}/sales/square", json={"accessToken": "sq-good-token", "environment": "sandbox"})
    body = r.json()
    assert body["source"] == "square" and body["label"] == "Pike St" and "sq-good-token" not in r.text
    assert fetched == {"token": "sq-good-token", "environment": "sandbox", "location_id": "L1"}
    assert last_sales_passed()["is_synthetic"] is True  # sandbox data is test data

    with sqlite3.connect(config.DB_PATH) as db:
        raw = db.execute("select sales_secret from businesses where id = ?", (business_id,)).fetchone()[0]
    assert raw and "sq-good-token" not in raw  # encrypted at rest
    assert "sq-good-token" not in owner.get(f"/api/business/{business_id}/sales").text


def test_toast_and_disconnect(owner, monkeypatch):
    business_id = onboard(owner, businessType="Taqueria", advisorReport=False)
    pos = sales._agent()[1]
    monkeypatch.setattr(pos, "check_toast", lambda cid, secret, guid: {"name": "Toasty Tacos"})
    r = owner.post(f"/api/business/{business_id}/sales/toast?refreshReport=false",
                   json={"clientId": "cid", "clientSecret": "secret-1", "restaurantGuid": "guid-1"}).json()
    assert r["source"] == "toast" and r["label"] == "Toasty Tacos" and r["reportStarted"] is False

    gone = owner.delete(f"/api/business/{business_id}/sales").json()
    assert gone == {"connected": False, "source": None}
    assert store.get_business(business_id)["sales_secret"] is None


def test_a_broken_connection_still_writes_the_report_and_says_why(owner, monkeypatch):
    business_id = onboard(owner, businessType="Cafe", advisorReport=False)
    pos = sales._agent()[1]
    monkeypatch.setattr(pos, "check_square", lambda token, env: [{"id": "L1", "name": "Pike St"}])
    monkeypatch.setattr(pos, "fetch_square", lambda *a, **k: 1 / 0)  # e.g. the owner revoked the token
    owner.post(f"/api/business/{business_id}/sales/square", json={"accessToken": "sq-good-token"})
    view = owner.get(f"/api/business/{business_id}/report").json()
    assert view["status"] == "complete" and last_sales_passed() is None
    assert "Reconnect it from the You tab" in view["report"]["advice"]["caveats"][0]


def test_the_sample_business_cant_connect_sales(client):
    import demo
    r = client.post(f"/api/business/{demo.BUSINESS_ID}/sales/csv", json={"content": OWN_CSV})
    assert r.status_code == 400
