"""Endpoints through FastAPI's TestClient: demo fixtures, and the live path with Ruth's collector and the
Claude scorer replaced by fakes. No network."""
import json
import sqlite3

import httpx2
import pytest
from fastapi.testclient import TestClient

import collect
import config
import main
import pipeline
import reports
import reviewer
import store

LIVE_KEYS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY")


@pytest.fixture()
def client(monkeypatch):
    for key in config.KEY_NAMES:
        monkeypatch.delenv(key, raising=False)
    with TestClient(main.app) as c:
        yield c


def test_health_reports_keys_without_values(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    body = client.get("/api/health").json()
    assert body["keys"]["ANTHROPIC_API_KEY"] is True and body["keys"]["TAVILY_API_KEY"] is False
    assert "sk-ant-secret" not in json.dumps(body)
    assert body["cache"]["demoPicks"] >= 30


def test_cuisines(client):
    body = client.get("/api/cuisines").json()
    assert [c["id"] for c in body] == ["sushi", "ramen", "steak", "pizza", "tacos"]
    assert [a["id"] for a in body[0]["attributes"]] == ["rice", "fish", "seaweed", "value", "wait"]


def test_demo_spots_shape(client):
    body = client.get("/api/spots", params={"cuisine": "sushi", "demo": "true"}).json()
    assert body["source"] == "demo" and body["demo"] is True and body["pickId"] == "sushi-hikari"
    spot = body["spots"][0]
    for key in ("id", "name", "lat", "lng", "address", "price", "distanceMi", "scores", "waitMinutes", "ambiancePct",
                "ambianceMentionRate", "bestAt", "reason", "reviewCount"):
        assert key in spot
    assert body["reviewsRead"] == sum(s["reviewCount"] for s in body["spots"])


def test_demo_mode_env(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    assert client.get("/api/spots", params={"cuisine": "ramen"}).json()["source"] == "demo"


def test_errors_are_plain_english(client):
    r = client.get("/api/spots", params={"cuisine": "pho"})
    assert r.status_code == 400 and "Unknown food type" in r.json()["error"]
    r = client.get("/api/spots", params={"cuisine": "sushi"})  # live, no keys
    assert r.status_code == 503 and "backend/.env" in r.json()["error"]
    r = client.get("/api/business/nope/insights")
    assert r.status_code == 404 and set(r.json()) == {"error"}
    r = client.post("/api/picks", json={"cuisine": "sushi"})
    assert r.status_code == 422 and "error" in r.json()


def test_spot_detail_has_walking_directions(client):
    body = client.get("/api/spots/sushi-umi", params={"demo": "true"}).json()
    assert body["mapsUrl"] == "https://www.google.com/maps/dir/?api=1&destination=47.6229,-122.3132&travelmode=walking"


def test_picks_are_anonymous(client):
    r = client.post("/api/picks", json={"cuisine": "sushi", "chosenSpotId": "sushi-umi", "comparedSpotIds": ["sushi-umi", "sushi-hikari"],
                                        "userId": "u-123", "email": "a@b.c"})
    assert r.json() == {"ok": True}
    with sqlite3.connect(config.DB_PATH) as db:
        cols = [c[1] for c in db.execute("pragma table_info(picks)")]
        last = db.execute("select * from picks order by id desc limit 1").fetchone()
    assert cols == ["id", "cuisine", "chosen_spot_id", "compared_spot_ids", "created_at", "demo"]
    assert "u-123" not in str(last) and "a@b.c" not in str(last)


def test_demo_rivals_and_insights(client):
    rivals = client.get("/api/business/biz-tamago/rivals", params={"days": 7}).json()
    assert rivals["demo"] is True
    assert rivals["picksWon"] >= 9 and rivals["picksLost"] >= 21
    top = rivals["rivals"][0]
    assert top["spotId"] == "sushi-hikari" and top["likelyBecause"]["gapLabel"] == "+9 min"
    assert {w["attribute"] for w in rivals["whereYouWin"]} >= {"seaweed"}

    insights = client.get("/api/business/biz-tamago/insights").json()
    assert insights["breakdown"][0]["attribute"] == "wait"  # the owner's first goal
    assert insights["reputation"] == 84 and 0 <= insights["edge"] <= 100 and insights["momentum"] is not None
    assert insights["wait"] == {"youMinutes": 18, "areaMinutes": 11}


def test_demo_places_search(client):
    body = client.get("/api/places/search", params={"q": "taco", "demo": "true"}).json()
    assert body["results"][0]["name"] == "Tacos Chukis"


# ---------- live path with fakes ----------

FAKE_REVIEWS = {
    "Kaito Sushi": ["Waited 20 minutes but the rice was warm and perfect.", "Cozy, beautiful room.", "Fish is so fresh."],
    "Tora Rolls": ["Line was 40 minutes, too long.", "Cheap rolls, decent fish.", "Loud and cramped inside."],
}


def fake_collect(cuisine, lat, lng, radius_mi, depth="fast"):
    spots = []
    for i, (name, texts) in enumerate(FAKE_REVIEWS.items()):
        spots.append({"id": f"spot-{collect.slug(name)}", "name": name, "address": f"{100 + i} Broadway E, Seattle, WA",
                      "lat": 47.62 + i / 1000, "lng": -122.32, "distanceMi": 0.2 + i / 10, "rating": 4.5, "review_count": 300,
                      "website": None, "hours": None, "details": {}, "failures": [], "collection_status": "complete",
                      "reviews": [{"text": t, "source_kind": "search_snippet", "source_url": "https://example.com"} for t in texts]})
    return {"collector": "fast", "spots": spots, "caveats": [], "raw": {"fake": True}, "label": "Capitol Hill, Seattle"}


def fake_score(name, cuisine, reviews, client=None):
    scores = {"Kaito Sushi": {"rice": 92, "fish": 88, "seaweed": None, "value": 70},
              "Tora Rolls": {"rice": 60, "fish": 72, "seaweed": None, "value": 90}}[name]
    labels = {"Kaito Sushi": ["none", "positive", "none"], "Tora Rolls": ["none", "none", "negative"]}[name]
    return {"scores": scores, "highlights": {"rice": "warm, perfectly seasoned rice", "value": "cheap, big rolls"},
            "ambianceLabels": labels, "summary": "Reviewers like it.", "reviewsUsed": reviews}


@pytest.fixture()
def live(client, monkeypatch):
    for key in LIVE_KEYS:
        monkeypatch.setenv(key, "test")
    monkeypatch.setattr(collect, "collect", fake_collect)
    monkeypatch.setattr(reviewer, "score_spot", fake_score)
    monkeypatch.setattr(pipeline.anthropic, "Anthropic", lambda: None)
    monkeypatch.setattr(reports, "_advisor", lambda: FakeAdvisor)  # onboarding queues an advisor report
    return client


class FakeAdvisor:
    """Ruth's advisor without network calls: returns the saved example report."""
    calls = []

    @staticmethod
    def run(*args, **kwargs):
        FakeAdvisor.calls.append((args, kwargs))
        return reports.example_report()


def test_live_spots_scored_then_cached(live):
    params = {"cuisine": "sushi", "lat": 47.6191, "lng": -122.3211, "radiusMi": 1}
    first = live.get("/api/spots", params=params).json()
    assert first["source"] == "live"
    kaito, tora = first["spots"]
    assert kaito["waitMinutes"] == 20 and tora["waitMinutes"] == 40  # medians of stated waits
    assert kaito["ambiancePct"] == 100 and kaito["ambianceMentionRate"] == 0.33
    assert tora["ambiancePct"] == 0
    assert kaito["scores"]["seaweed"] is None  # unmentioned stays null
    assert first["pickId"] == kaito["id"] and "Highest average" in first["pickReason"]
    assert kaito["bestAt"] in ("Best rice", "Shortest wait", "Best fish", "Best vibe") and tora["bestAt"] == "Best value"
    assert tora["reason"] == "cheap, big rolls" and kaito["sourceKinds"] == ["search_snippet"]
    assert live.get("/api/spots", params=params).json()["source"] == "cache"

    detail = live.get(f"/api/spots/{kaito['id']}").json()
    assert detail["reviews"][0]["sourceKind"] == "search_snippet" and detail["mapsUrl"].endswith("travelmode=walking")


def test_onboard_scores_in_background_and_links_the_spot(live, monkeypatch):
    monkeypatch.setattr(pipeline.geo, "place_details", lambda place_id: None)
    r = live.post("/api/business/onboard", json={
        "name": "Kaito Sushi", "address": "100 Broadway E, Seattle, WA", "lat": 47.6195, "lng": -122.3205, "cuisine": "sushi",
        "goals": ["Value", "shorter waits"], "questionnaire": {"offerings": "Omakase and rolls", "customers": "", "extra": "ignored"}})
    business_id = r.json()["businessId"]
    b = store.get_business(business_id)
    assert b["scoring_status"] == "complete" and b["spot_id"] == "spot-kaito-sushi"
    assert b["profile"] == {"offerings": "Omakase and rolls"}

    store.add_pick("sushi", "spot-tora-rolls", ["spot-kaito-sushi", "spot-tora-rolls"])
    insights = live.get(f"/api/business/{business_id}/insights").json()
    assert [row["attribute"] for row in insights["breakdown"]][:2] == ["value", "wait"]
    assert insights["status"] == "complete" and insights["demo"] is False
    rivals = live.get(f"/api/business/{business_id}/rivals").json()
    assert rivals["rivals"][0]["spotId"] == "spot-tora-rolls"
    assert rivals["rivals"][0]["likelyBecause"]["attribute"] == "value"
    # demo picks never count for a real business
    assert rivals["picksLost"] == 1


# ---------- the real Claude request shape, against a mocked HTTP transport ----------

def test_reviewer_request_shape():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        out = {"attributes": [{"attribute": "rice", "score": 91, "mentions": 2, "highlight": "warm rice"},
                              {"attribute": "fish", "score": 150, "mentions": 1, "highlight": "fresh"},
                              {"attribute": "seaweed", "score": 60, "mentions": 0, "highlight": None},
                              {"attribute": "made-up", "score": 99, "mentions": 3, "highlight": "x"}],
               "ambiance": [{"review": 2, "ambiance": "positive"}, {"review": 9, "ambiance": "negative"}],
               "summary": "Warm rice, fresh fish."}
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": config.SCORING_MODEL,
            "content": [{"type": "text", "text": json.dumps(out)}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10}})

    client = reviewer.anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    reviews = [{"text": "Rice was warm."}, {"text": "Lovely room, fresh fish."}, {"text": "Rice again great."}]
    result = reviewer.score_spot("Kaito Sushi", "sushi", reviews, client)

    assert seen["body"]["model"] == "claude-sonnet-5-5"
    assert seen["body"]["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in seen["beta"]
    assert seen["body"]["output_config"]["effort"] == "medium" and "format" in seen["body"]["output_config"]
    assert "[2] Lovely room, fresh fish." in seen["body"]["messages"][0]["content"]
    assert result["scores"] == {"rice": 91, "fish": 100, "seaweed": None, "value": None}  # clamped, unmentioned → null
    assert "made-up" not in result["scores"]
    assert result["ambianceLabels"] == ["none", "positive", "none"]


def test_knehas_recommendations_endpoint_still_works(client):
    r = client.post("/api/recommendations", params={"demo": "true"}, json={
        "profile": {"name": "Rise & Knead", "category": "bakery", "waitMin": 6},
        "competitors": [{"name": "A", "waitMin": 9}, {"name": "B", "waitMin": 5}]})
    assert r.status_code == 200
    tip = r.json()["recommendations"][0]
    assert tip["id"] == "demo-wait" and "median wait 7" in tip["evidence"]
