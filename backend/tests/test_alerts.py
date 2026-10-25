"""Alerts: stock and top-rated triggers, Ruth's monitor through the SQLite adapter, Square parsing, endpoints.
No network: Ruth's research and diff calls, Square and Claude are all replaced by fakes."""
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

import alerts
import auth
import config
import cuisines
import main
import pipeline
import square_inventory
import store

WHEN = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)


def item(vid, qty, name="Toro"):
    return {"variationId": vid, "name": name, "quantity": qty}


# ---------- stock-increase trigger ----------

class TestStockEvents:
    def test_meaningful_increase_is_fresh(self):
        events = alerts.stock_events({"v1": 4.0}, [item("v1", 20.0)], threshold=5)
        assert [e["type"] for e in events] == ["fresh"]

    def test_restock_from_zero_needs_ten_units(self):
        assert [e["type"] for e in alerts.stock_events({"v1": 0.0}, [item("v1", 12.0)], 5)] == ["fresh"]
        assert alerts.stock_events({"v1": 0.0}, [item("v1", 9.0)], 5) == []

    def test_small_or_relative_bumps_are_not_fresh(self):
        assert alerts.stock_events({"v1": 30.0}, [item("v1", 42.0)], 5) == []  # +12 is under half of 30
        assert alerts.stock_events({"v1": 30.0}, [item("v1", 45.0)], 5)[0]["type"] == "fresh"

    def test_first_snapshot_is_never_fresh(self):
        assert alerts.stock_events({}, [item("v1", 50.0)], 5) == []

    def test_low_when_crossing_the_threshold_only(self):
        assert [e["type"] for e in alerts.stock_events({"v1": 12.0}, [item("v1", 3.0)], 5)] == ["low"]
        assert [e["type"] for e in alerts.stock_events({}, [item("v1", 2.0)], 5)] == ["low"]
        assert alerts.stock_events({"v1": 3.0}, [item("v1", 2.0)], 5) == []  # already low: no repeat

    def test_unknown_counts_never_trigger(self):
        assert alerts.stock_events({"v1": 40.0}, [item("v1", None)], 5) == []


BIZ = {"id": "biz-1", "name": "Kaito Sushi", "business_type": "sushi", "spot_id": "spot-kaito", "lat": 47.62, "lng": -122.32,
       "share_stock_alerts": 1, "low_stock_threshold": 5}
FRESH = [{"type": "fresh", "variationId": "v1", "name": "Bluefin Toro", "before": 2.0, "now": 37.0}]
LOW = [{"type": "low", "variationId": "v2", "name": "Uni", "before": 9.0, "now": 3.0}]


class TestStockAlerts:
    def test_fresh_is_public_without_counts(self):
        [a] = alerts.stock_alerts(BIZ, [], FRESH, when=WHEN)
        assert a["kind"] == "fresh_stock" and a["audience"] == "consumer"
        assert a["title"] == "Kaito Sushi just got a fresh shipment of bluefin toro"
        assert not any(ch.isdigit() for ch in a["title"] + a["detail"])  # never expose exact stock counts

    def test_fresh_needs_opt_in(self):
        closed = {**BIZ, "share_stock_alerts": 0}
        assert alerts.stock_alerts(closed, [], FRESH, when=WHEN) == []
        assert len(alerts.stock_alerts(closed, ["Share stock alerts"], FRESH, when=WHEN)) == 1  # a goal also opts in

    def test_low_is_for_the_owner_with_the_count(self):
        [a] = alerts.stock_alerts({**BIZ, "share_stock_alerts": 0}, [], LOW, when=WHEN)
        assert (a["kind"], a["audience"], a["business_id"]) == ("low_stock", "business", "biz-1")
        assert a["detail"].startswith("3 left")


# ---------- top-rated trigger ----------

ATTRS = cuisines.compare_attributes("sushi")


def spot(id, rice, wait=None, name=None):
    return {"id": id, "name": name or id, "scores": {"rice": rice, "fish": None, "seaweed": None, "value": None},
            "waitMinutes": wait, "ambiancePct": None, "lat": 47.62, "lng": -122.32, "_highlights": {"rice": "warm rice"}}


class TestTopRated:
    def test_first_scoring_is_a_baseline(self):
        assert alerts.top_rated_alerts("sushi", "k", None, [spot("a", 90), spot("b", 80)], when=WHEN) == []

    def test_new_number_one_makes_one_alert(self):
        before = [spot("a", 90, wait=12), spot("b", 80, wait=8)]
        after = [spot("a", 85, wait=12), spot("b", 93, wait=8, name="Umi Counter")]
        [a] = alerts.top_rated_alerts("sushi", "k", before, after, when=WHEN)  # wait leader unchanged → no alert
        assert a["kind"] == "top_rated" and a["audience"] == "consumer" and a["spot_id"] == "b"
        assert a["title"] == "Umi Counter is now #1 for rice"
        assert "93/100" in a["detail"] and "warm rice" in a["detail"]

    def test_same_leader_or_a_tie_is_quiet(self):
        assert alerts.top_rated_alerts("sushi", "k", [spot("a", 90), spot("b", 80)], [spot("a", 95), spot("b", 80)]) == []
        assert alerts.top_rated_alerts("sushi", "k", [spot("a", 90), spot("b", 80)], [spot("a", 88), spot("b", 88)]) == []

    def test_wait_leader_title(self):
        [a] = alerts.top_rated_alerts("sushi", "k", [spot("a", None, 10), spot("b", None, 14)],
                                      [spot("a", None, 10), spot("b", None, 6, name="Pike Roll")], when=WHEN)
        assert a["title"] == "Pike Roll now has the shortest wait" and "About 6 min" in a["detail"]


# ---------- endpoints and integrations ----------

@pytest.fixture()
def client(monkeypatch):
    for key in [*config.KEY_NAMES, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]:
        monkeypatch.delenv(key, raising=False)
    with TestClient(main.app) as c:
        yield c


def test_demo_alerts_cover_every_kind(client):
    consumer = client.get("/api/alerts", params={"audience": "consumer", "demo": "true", "radiusMi": 1}).json()
    business = client.get("/api/alerts", params={"audience": "business", "businessId": "biz-tamago"}).json()
    kinds = {a["kind"] for a in consumer + business}
    assert {"new_spot", "closed", "price_change", "fresh_stock", "top_rated", "low_stock", "new_competitor",
            "hours_change", "rating_change", "review_trend"} <= kinds
    assert 9 <= len(consumer + business) <= 13
    assert {a["audience"] for a in consumer} == {"consumer"} and {a["audience"] for a in business} == {"business"}
    keys = {"id", "kind", "audience", "spotId", "cuisine", "title", "detail", "distanceMi", "createdAt", "read"}
    assert all(keys <= set(a) for a in consumer + business)
    assert [a["createdAt"] for a in consumer] == sorted((a["createdAt"] for a in consumer), reverse=True)


def test_read_flow(client):
    first = client.get("/api/alerts", params={"demo": "true"}).json()[0]
    assert first["read"] is False
    assert client.post(f"/api/alerts/{first['id']}/read").json() == {"ok": True}
    again = next(a for a in client.get("/api/alerts", params={"demo": "true"}).json() if a["id"] == first["id"])
    assert again["read"] is True


def test_business_alerts_need_a_business(client):
    r = client.get("/api/alerts", params={"audience": "business"})
    assert r.status_code == 400 and "businessId" in r.json()["error"]


def test_stock_check_end_to_end(client, monkeypatch):
    shares = store.create_business(name="Kaito Sushi", business_type="sushi", location="Capitol Hill", lat=47.6195, lng=-122.3205)
    private = store.create_business(name="Quiet Rolls", business_type="sushi", location="Capitol Hill", lat=47.6196, lng=-122.3206)
    store.update_business(shares, share_stock_alerts=1)
    counts = iter([[item("v1", 2.0), item("v2", 40.0, "Uni")], [item("v1", 37.0), item("v2", 3.0, "Uni")]] * 2)
    monkeypatch.setattr(square_inventory, "fetch_inventory", lambda *a, **k: {"locationId": "L1", "items": next(counts)})

    for business_id in (shares, private):
        assert alerts.check_stock(business_id)["alertsAdded"] == 1  # first snapshot: toro starts below 5 → low
        assert alerts.check_stock(business_id)["alertsAdded"] == (2 if business_id == shares else 1)  # fresh toro (+ public if opted in), low uni

    near = {"audience": "consumer", "lat": 47.6195, "lng": -122.3205, "radiusMi": 1}
    public = [a for a in client.get("/api/alerts", params=near).json() if a["kind"] == "fresh_stock"]
    assert [a["title"] for a in public] == ["Kaito Sushi just got a fresh shipment of toro"]
    owner = client.get("/api/alerts", params={"audience": "business", "businessId": shares}).json()
    assert sorted(a["title"] for a in owner) == ["Low stock: Toro", "Low stock: Uni"]
    far = client.get("/api/alerts", params={**near, "lat": 47.70}).json()
    assert not any(a["kind"] == "fresh_stock" for a in far)  # outside the radius


def test_top_rated_alert_from_a_rescore(client, monkeypatch):
    import collect
    import reviewer
    from tests.test_api import fake_collect

    for key in pipeline.LIVE_KEYS:
        monkeypatch.setenv(key, "test")
    monkeypatch.setattr(collect, "collect", fake_collect)
    monkeypatch.setattr(pipeline.anthropic, "Anthropic", lambda: None)
    rice = {"Kaito Sushi": 92, "Tora Rolls": 60}

    def fake_score(name, cuisine, reviews, client=None):
        return {"scores": {"rice": rice[name], "fish": 70, "seaweed": None, "value": 70}, "highlights": {"rice": f"{name} rice"},
                "ambianceLabels": ["none"] * len(reviews), "summary": "", "reviewsUsed": reviews}

    monkeypatch.setattr(reviewer, "score_spot", fake_score)
    params = {"cuisine": "sushi", "lat": 47.61, "lng": -122.33, "radiusMi": 1}
    client.get("/api/spots", params=params)  # baseline
    rice.update({"Kaito Sushi": 70, "Tora Rolls": 95})
    client.get("/api/spots", params={**params, "refresh": "true"})
    top = [a for a in client.get("/api/alerts", params={"lat": 47.61, "lng": -122.33}).json() if a["kind"] == "top_rated"]
    assert [a["title"] for a in top] == ["Tora Rolls is now #1 for rice"]


def test_ruths_monitor_runs_through_the_sqlite_adapter(client, monkeypatch):
    monkeypatch.setattr(alerts, "supabase_configured", lambda: False)  # this test covers the SQLite path, whatever .env holds
    monkeypatch.setattr(auth, "enabled", lambda: False)  # ...and no sign-in (agent/ reloads the root .env on import)
    monitor = alerts._monitor_module()
    business_id = store.create_business(name="Kaito Sushi", business_type="sushi", location="Capitol Hill, Seattle",
                                        address="100 Broadway E, Seattle, WA", lat=47.6195, lng=-122.3205)
    store.upsert_spot({"id": "spot-tora-rolls", "name": "Tora Rolls", "lat": 47.6201, "lng": -122.3211})
    snapshots = iter([
        {"business": "Kaito Sushi", "type": "sushi", "location": "x", "date": "2026-10-20", "competitors": [{"name": "Tora Rolls", "address": "101 Broadway E"}]},
        {"business": "Kaito Sushi", "type": "sushi", "location": "x", "date": "2026-10-25", "competitors": [{"name": "Tora Rolls", "address": "101 Broadway E"}]},
    ])
    seen = {}

    def baseline(name, business_type, location):
        return next(snapshots)

    def recheck(name, business_type, location, tracked):
        seen["tracked"] = [f"{c['name']}, {c['address']}" for c in tracked]
        return next(snapshots)

    monkeypatch.setattr(monitor.fast_competitors, "run", baseline)
    monkeypatch.setattr(monitor.fast_competitors, "run_tracked", recheck)
    monkeypatch.setattr(monitor, "diff", lambda prev, cur: monitor.ChangeReport(changes=[
        monitor.Change(kind="price_change", competitor="Tora Rolls", before="Spicy tuna roll: $9", after="Spicy tuna roll: $11",
                       evidence="menu page", why_it_matters="You are now $2 cheaper on your best seller."),
        monitor.Change(kind="rating_change", competitor="Tora Rolls", before="4.2", after="4.6", evidence="Google",
                       why_it_matters="They're gaining reviews fast."),
    ], message="Tora Rolls raised prices."))

    assert alerts.run_monitor(business_id) == {"baseline": True, "changes": 0}
    assert alerts.run_monitor(business_id) == {"baseline": False, "changes": 2}
    assert seen["tracked"] == ["Tora Rolls, 101 Broadway E"]  # Ruth's monitor re-checks the baseline's competitors

    owner = client.get("/api/alerts", params={"audience": "business", "businessId": business_id}).json()
    assert {a["kind"] for a in owner} == {"price_change", "rating_change"}
    assert "You are now $2 cheaper" in next(a["detail"] for a in owner if a["kind"] == "price_change")
    public = client.get("/api/alerts", params={"lat": 47.6195, "lng": -122.3205}).json()
    price = [a for a in public if a["kind"] == "price_change"]
    assert len(price) == 1 and price[0]["spotId"] == "spot-tora-rolls" and price[0]["distanceMi"] < 0.1
    assert price[0]["detail"] == "Spicy tuna roll: $9 → Spicy tuna roll: $11"  # no owner-only advice in public
    assert not any(a["kind"] == "rating_change" for a in public)  # only public kinds reach consumers


def test_square_inventory_parsing(monkeypatch):
    monkeypatch.setenv("SQUARE_ACCESS_TOKEN", "test")
    monkeypatch.setenv("SQUARE_ENVIRONMENT", "sandbox")
    monkeypatch.delenv("SQUARE_LOCATION_ID", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "connect.squareupsandbox.com" and request.headers["Square-Version"] == "2026-09-16"
        if request.url.path == "/v2/locations":
            return httpx.Response(200, json={"locations": [{"id": "L1", "status": "ACTIVE"}, {"id": "L0", "status": "INACTIVE"}]})
        if request.url.path == "/v2/catalog/list":
            return httpx.Response(200, json={"objects": [
                {"id": "I1", "type": "ITEM", "item_data": {"name": "Toro", "variations": [
                    {"id": "V1", "type": "ITEM_VARIATION", "item_variation_data": {"item_id": "I1", "name": "Regular", "track_inventory": True}},
                    {"id": "V2", "type": "ITEM_VARIATION", "item_variation_data": {"item_id": "I1", "name": "Large", "track_inventory": False,
                     "location_overrides": [{"location_id": "L1", "track_inventory": True}]}}]}},
                {"id": "I2", "type": "ITEM", "item_data": {"name": "Tea", "variations": [
                    {"id": "V3", "type": "ITEM_VARIATION", "item_variation_data": {"item_id": "I2", "name": "Regular", "track_inventory": False}}]}},
                {"id": "I3", "type": "ITEM", "present_at_all_locations": False, "present_at_location_ids": ["L9"], "item_data": {"name": "Away", "variations": [
                    {"id": "V4", "type": "ITEM_VARIATION", "item_variation_data": {"item_id": "I3", "track_inventory": True}}]}},
            ]})
        assert request.url.path == "/v2/inventory/counts/batch-retrieve"
        return httpx.Response(200, json={"counts": [
            {"catalog_object_id": "V1", "location_id": "L1", "state": "IN_STOCK", "quantity": "4", "calculated_at": "2026-10-25T10:00:00Z"},
            {"catalog_object_id": "V1", "location_id": "L1", "state": "IN_STOCK", "quantity": "18", "calculated_at": "2026-10-25T12:00:00Z"},
            {"catalog_object_id": "V2", "location_id": "L1", "state": "SOLD", "quantity": "9"},
        ]})

    result = square_inventory.fetch_inventory(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result["locationId"] == "L1"
    assert result["items"] == [{"variationId": "V1", "name": "Toro", "quantity": 18.0},  # newest count wins
                               {"variationId": "V2", "name": "Toro (Large)", "quantity": None}]  # tracked by override; no IN_STOCK count = unknown
