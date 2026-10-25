"""store.py → Supabase writes and scripts/sync_to_supabase.py, against a fake Supabase REST API (no network)."""
import json
import sys
from pathlib import Path

import httpx
import pytest

import demo
import store
import supabase_rest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sync_to_supabase  # noqa: E402

REMOTE_BIZ = "11111111-2222-3333-4444-555555555555"


class FakeSupabase:
    """Records every request; answers GETs from `tables`."""

    def __init__(self, tables=None, fail=False):
        self.requests, self.tables, self.fail = [], tables or {}, fail

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        table = request.url.path.rsplit("/", 1)[-1]
        self.requests.append({"method": request.method, "table": table, "params": dict(request.url.params),
                              "headers": request.headers, "body": body})
        if self.fail:
            return httpx.Response(401, json={"message": "Invalid API key"})
        if request.method == "GET":
            return httpx.Response(200, json=self.tables.get(table, []))
        return httpx.Response(201)

    def sent(self, table, method="POST"):
        return [r for r in self.requests if r["table"] == table and r["method"] == method]


@pytest.fixture
def fake(monkeypatch):
    def make(**kw):
        server = FakeSupabase(**kw)
        supabase_rest.use_client(httpx.Client(transport=httpx.MockTransport(server)))
        return server

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_test")
    for key in ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "SQUARE_ACCESS_TOKEN"):
        monkeypatch.setenv(key, "")
    supabase_rest.errors.clear()
    store.init()
    yield make
    supabase_rest.use_client(None)
    supabase_rest.errors.clear()


def test_off_without_keys(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    assert not supabase_rest.configured()
    assert supabase_rest.select("spots", {}) is None
    assert supabase_rest.insert("picks", {"a": 1}) is False


def test_secret_key_headers(fake):
    server = fake()
    store.add_pick("sushi", "sushi-hikari", ["sushi-hikari", "sushi-umi"])
    sent = server.sent("picks")[0]
    assert sent["headers"]["apikey"] == "sb_secret_test"
    assert "authorization" not in sent["headers"]  # sb_ keys go in apikey only, like Ruth's SupabaseStore
    assert sent["body"] == [{"cuisine": "sushi", "chosen_spot_id": "sushi-hikari", "compared_spot_ids": ["sushi-hikari", "sushi-umi"],
                             "demo": False, "created_at": sent["body"][0]["created_at"]}]


def test_legacy_jwt_key_also_goes_in_authorization(fake, monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOi.test.jwt")
    server = fake()
    store.add_pick("sushi", "a", ["a"])
    assert server.sent("picks")[0]["headers"]["authorization"] == "Bearer eyJhbGciOi.test.jwt"


def test_area_goes_to_spots_and_scores_with_the_pick(fake):
    server = fake()
    payload = demo.spots("sushi")
    store.put_area("sushi:47.619:-122.321:1.00", cuisine="sushi", lat=47.619, lng=-122.321, radius_mi=1.0,
                   payload=payload, status="complete")
    spots = server.sent("spots")[0]["body"]
    assert {s["id"] for s in spots} == {s["id"] for s in payload["spots"]}
    hikari = next(s for s in spots if s["id"] == "sushi-hikari")
    assert (hikari["street"], hikari["phone"], hikari["open_until"]) == ("E Pike St", "(206) 555-0101", "10 PM")
    reset = server.sent("spot_scores", "PATCH")[0]
    assert reset["params"] == {"cuisine": "eq.sushi", "area": "eq.capitol-hill", "is_pick": "is.true"}
    scores = server.sent("spot_scores")[0]
    assert scores["params"]["on_conflict"] == "spot_id,cuisine"
    pick = [s for s in scores["body"] if s["is_pick"]]
    assert [s["spot_id"] for s in pick] == ["sushi-hikari"]
    assert pick[0]["best_at"] == "Best rice" and pick[0]["scores"]["rice"] == 93


def test_picks_are_read_from_supabase_when_on(fake):
    from datetime import datetime, timedelta, timezone
    row = {"cuisine": "sushi", "chosen_spot_id": "sushi-umi", "compared_spot_ids": ["sushi-umi", "biz-x"],
           "created_at": "2026-10-25T20:00:00+00:00", "demo": False}
    server = fake(tables={"picks": [row]})
    assert store.picks_since("sushi", datetime.now(timezone.utc) - timedelta(days=7), include_demo=False) == [row]
    assert server.sent("picks", "GET")[0]["params"]["demo"] == "is.false"


def test_picks_fall_back_to_sqlite_when_supabase_fails(fake):
    from datetime import datetime, timedelta, timezone
    fake(fail=True)
    store.add_pick("ramen", "ramen-x", ["ramen-x"])
    local = store.picks_since("ramen", datetime.now(timezone.utc) - timedelta(days=1), include_demo=False)
    assert [p["chosen_spot_id"] for p in local][-1] == "ramen-x"
    assert supabase_rest.errors  # recorded, not raised


def test_alerts_consumer_always_business_only_when_linked(fake):
    server = fake()
    unlinked = store.create_business(name="Shop A", business_type="sushi", location="Capitol Hill")
    linked = store.create_business(name="Shop B", business_type="sushi", location="Capitol Hill")
    store.update_business(linked, supabase_business_id=REMOTE_BIZ)
    base = {"title": "t", "detail": "d", "cuisine": "sushi"}
    store.add_alert({**base, "kind": "top_rated", "audience": "consumer", "dedupe_key": "c-1"})
    store.add_alert({**base, "kind": "low_stock", "audience": "business", "business_id": unlinked, "dedupe_key": "b-1"})
    store.add_alert({**base, "kind": "low_stock", "audience": "business", "business_id": linked, "dedupe_key": "b-2"})
    store.add_alert({**base, "kind": "top_rated", "audience": "consumer", "dedupe_key": "c-1"})  # duplicate: not resent
    sent = [r["body"][0] for r in server.sent("alerts")]
    assert [(a["audience"], a["business_id"]) for a in sent] == [("consumer", None), ("business", REMOTE_BIZ)]


def test_sync_demo_without_ai_keys(fake, capsys):
    server = fake(tables={"businesses": [{"id": REMOTE_BIZ, "name": "Tamago Sushi", "business_type": "sushi restaurant",
                                         "location": "Capitol Hill, Seattle", "cuisine": "sushi", "goals": ["Rice"],
                                         "share_stock_alerts": True, "low_stock_threshold": 3}],
                          "changes": []})
    sys.argv = ["sync_to_supabase.py", "--demo"]
    assert sync_to_supabase.main() == 0
    out = capsys.readouterr().out
    assert "sushi  sample spots (demo)" in out and "Tamago Sushi (sushi)" in out
    assert len(server.sent("spot_scores")) == 5  # one upsert per food type
    assert all(s["demo"] for r in server.sent("spot_scores") for s in r["body"])
    public = [a for r in server.sent("alerts") for a in r["body"]]
    assert public and all(a["audience"] == "consumer" and a["demo"] for a in public)
    local = store.business_for_remote(REMOTE_BIZ)
    assert (local["business_type"], local["share_stock_alerts"], local["low_stock_threshold"]) == ("sushi", 1, 3.0)
    assert store.get_goals(local["id"]) == ["Rice"]


def test_sync_stops_without_supabase(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "")
    sys.argv = ["sync_to_supabase.py"]
    assert sync_to_supabase.main() == 1
    assert "SUPABASE_URL" in capsys.readouterr().out


def test_sync_fails_loudly_when_writes_fail(fake, capsys):
    fake(fail=True)
    sys.argv = ["sync_to_supabase.py", "--demo"]
    assert sync_to_supabase.main() == 1
    assert "write(s) failed" in capsys.readouterr().out


def test_change_alerts_owner_and_public(fake, monkeypatch):
    server = fake()
    local = store.get_business(store.create_business(name="Shop", business_type="sushi", location="Capitol Hill"))
    changes = [{"id": "c1", "business_id": REMOTE_BIZ, "kind": "price_change", "competitor_name": "Umi Counter",
                "before": "$14", "after": "$16", "why_it_matters": "Your nigiri is now cheaper.", "created_at": "2026-10-25T20:00:00+00:00"},
               {"id": "c2", "business_id": REMOTE_BIZ, "kind": "hours_change", "competitor_name": "Umi Counter",
                "before": "9pm", "after": "11pm", "why_it_matters": "", "created_at": "2026-10-25T20:00:00+00:00"}]
    monkeypatch.setattr(store, "remote_changes", lambda remote_id, since: changes if remote_id == REMOTE_BIZ else [])
    assert sync_to_supabase.change_alerts(local, REMOTE_BIZ) == 3
    rows = server.sent("alerts")[0]["body"]
    assert [(r["id"], r["audience"]) for r in rows] == [("chg-c1", "business"), ("chg-pub-c1", "consumer"), ("chg-c2", "business")]
    assert "why" not in rows[1]["detail"].lower() and "cheaper" not in rows[1]["detail"]  # owner advice stays private
