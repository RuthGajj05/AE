"""store.py → the Lovable app's Supabase tables, and scripts/sync_to_supabase.py, against a fake Supabase REST API
(no network). Column sets are Lovable's exactly."""
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import demo
import store
import supabase_rest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sync_to_supabase  # noqa: E402

# Lovable's tables (public schema), minus columns with database defaults the backend never sends (ids, created_at).
SPOTS = {"id", "name", "cuisine", "letter", "lat", "lng", "address", "price", "distance_mi", "hours", "phone"}
SPOT_SCORES = {"spot_id", "attribute", "score", "wait_minutes", "ambiance_pct", "ambiance_mention_rate", "best_at", "reason", "is_pick"}
PICKS = {"cuisine", "chosen_spot_id", "compared_spot_ids", "created_at"}
ALERTS = {"id", "kind", "audience", "spot_id", "title", "detail", "distance_mi", "created_at"}

OWNER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RUTH_BIZ = "11111111-2222-3333-4444-555555555555"


class FakeSupabase:
    """Records every request; answers GETs from `tables` (a table missing from `missing` answers 404)."""

    def __init__(self, tables=None, fail=False, missing=()):
        self.requests, self.tables, self.fail, self.missing = [], tables or {}, fail, set(missing)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        table = request.url.path.rsplit("/", 1)[-1]
        self.requests.append({"method": request.method, "table": table, "params": dict(request.url.params),
                              "headers": request.headers, "body": body})
        if self.fail:
            return httpx.Response(401, json={"message": "Invalid API key"})
        if table in self.missing:
            return httpx.Response(404, json={"code": "PGRST205", "message": f"Could not find the table 'public.{table}'"})
        if request.method == "GET":
            return httpx.Response(200, json=self.tables.get(table, []))
        if request.method == "POST" and "return=representation" in request.headers.get("prefer", ""):
            return httpx.Response(201, json=[{"id": RUTH_BIZ, **body[0]}])
        return httpx.Response(201)

    def sent(self, table, method="POST"):
        return [r for r in self.requests if r["table"] == table and r["method"] == method]

    def rows(self, table):
        return [row for r in self.sent(table) for row in r["body"]]


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
    assert set(sent["body"][0]) == PICKS
    assert sent["body"][0]["compared_spot_ids"] == ["sushi-hikari", "sushi-umi"]


def test_legacy_jwt_key_also_goes_in_authorization(fake, monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOi.test.jwt")
    server = fake()
    store.add_pick("sushi", "a", ["a"])
    assert server.sent("picks")[0]["headers"]["authorization"] == "Bearer eyJhbGciOi.test.jwt"


def test_demo_picks_never_reach_supabase(fake):
    server = fake()
    store.add_pick("sushi", "a", ["a"], demo=True)
    assert server.sent("picks") == []


def test_area_matches_lovables_spots_and_spot_scores(fake):
    server = fake(tables={"spots": [{"id": "sushi-hikari"}, {"id": "sushi-old"}]})
    store.publish_area(demo.spots("sushi"), demo=True)

    spots = server.rows("spots")
    assert all(set(s) == SPOTS for s in spots)
    assert [(s["letter"], s["id"]) for s in spots] == [
        ("A", "sushi-hikari"), ("B", "sushi-umi"), ("C", "sushi-nori-house"), ("D", "sushi-pike-roll")]  # localhost's A–D
    hikari = spots[0]
    assert (hikari["cuisine"], hikari["price"], hikari["hours"], hikari["phone"]) == ("sushi", "$$$", "10 PM", "(206) 555-0101")
    assert hikari["distance_mi"] == 0.4  # walk along the grid from the middle of Capitol Hill, as the app shows

    # Old rows for this food type are cleared first (no unique key on spot + attribute), and a spot that dropped out goes.
    assert server.sent("spot_scores", "DELETE")[0]["params"]["spot_id"].startswith("in.(")
    assert server.sent("spots", "DELETE")[0]["params"] == {"id": "in.(sushi-old)"}

    scores = server.rows("spot_scores")
    assert all(set(r) == SPOT_SCORES for r in scores)
    assert len(scores) == 4 * 4  # 4 spots × rice, fish, seaweed, value
    rice = next(r for r in scores if r["spot_id"] == "sushi-hikari" and r["attribute"] == "rice")
    assert rice == {"spot_id": "sushi-hikari", "attribute": "rice", "score": 93, "wait_minutes": 9, "ambiance_pct": 81,
                    "ambiance_mention_rate": "1 of 4 reviews", "best_at": "Best rice",
                    "reason": "Reviewers keep praising the warm, well-seasoned rice.", "is_pick": True}
    assert {r["spot_id"] for r in scores if r["is_pick"]} == {"sushi-hikari"}


def test_live_area_leads_with_the_pick_and_rounds_to_integers(fake):
    server = fake()
    payload = demo.spots("ramen")
    for s in payload["spots"]:
        s["pick"] = False
    payload["spots"][-1].update(pick=True, waitMinutes=17.5)
    store.put_area("ramen:47.619:-122.321:1.00", cuisine="ramen", lat=47.619, lng=-122.321, radius_mi=1.0,
                   payload=payload, status="complete")
    spots = server.rows("spots")
    assert spots[0]["id"] == payload["spots"][-1]["id"] and spots[0]["letter"] == "A"
    assert {r["wait_minutes"] for r in server.rows("spot_scores") if r["spot_id"] == spots[0]["id"]} == {18}


def test_other_areas_are_not_sent(fake):
    server = fake()
    store.put_area("sushi:47.700:-122.300:1.00", cuisine="sushi", lat=47.7, lng=-122.3, radius_mi=1.0,
                   payload=demo.spots("sushi"), status="complete")
    assert server.requests == []


def test_mention_text():
    assert store.mention_text(0.25) == "1 of 4 reviews"
    assert store.mention_text(0.33) == "1 of 3 reviews"
    assert store.mention_text(None) is None and store.mention_text(0) is None


def test_picks_are_read_from_supabase_plus_local_demo_picks(fake):
    row = {"cuisine": "sushi", "chosen_spot_id": "sushi-umi", "compared_spot_ids": ["sushi-umi", "biz-x"],
           "created_at": "2099-01-01T00:00:00+00:00"}
    server = fake(tables={"picks": [row]})
    store.add_pick("sushi", "sushi-hikari", ["sushi-hikari"], demo=True)
    week = datetime.now(timezone.utc) - timedelta(days=7)
    assert store.picks_since("sushi", week, include_demo=False) == [{**row, "demo": 0}]
    both = store.picks_since("sushi", week, include_demo=True)
    assert [p["chosen_spot_id"] for p in both][-1] == "sushi-umi" and any(p["demo"] for p in both)
    assert "demo" not in server.sent("picks", "GET")[0]["params"]["select"]


def test_picks_fall_back_to_sqlite_when_supabase_fails(fake):
    fake(fail=True)
    store.add_pick("ramen", "ramen-x", ["ramen-x"])
    local = store.picks_since("ramen", datetime.now(timezone.utc) - timedelta(days=1), include_demo=False)
    assert [p["chosen_spot_id"] for p in local][-1] == "ramen-x"
    assert supabase_rest.errors  # recorded, not raised


def test_alerts_match_lovables_columns(fake):
    server = fake()
    base = {"title": "Hikari Sushi Bar is now #1 for rice", "detail": "d", "cuisine": "sushi", "spot_id": "sushi-hikari",
            "lat": 47.6152, "lng": -122.3185}
    store.add_alert({**base, "id": "top-1", "kind": "top_rated", "audience": "consumer", "dedupe_key": "c-1"})
    store.add_alert({**base, "id": "top-2", "kind": "top_rated", "audience": "consumer", "dedupe_key": "c-1"})  # duplicate
    store.add_alert({"id": "low-1", "kind": "low_stock", "audience": "business", "title": "Low stock: Uni", "detail": "3 left"})
    rows = server.rows("alerts")
    assert all(set(r) == ALERTS for r in rows)
    assert [r["audience"] for r in rows] == ["consumer", "business"]
    assert rows[0]["id"] == str(uuid.uuid5(uuid.NAMESPACE_URL, "crumbs-alert:top-1"))  # stable uuid, so re-sending is a no-op
    assert uuid.UUID(rows[1]["id"])
    assert rows[0]["distance_mi"] == 0.29 and rows[1]["distance_mi"] is None
    assert server.sent("alerts")[0]["params"]["on_conflict"] == "id"


PROFILE = {"user_id": OWNER, "display_name": "Jagger", "business_name": "Tamago Sushi",
           "business_address": "1520 E Olive Way, Seattle", "cuisine": "Sushi"}


def test_sync_demo_without_ruths_tables(fake, capsys):
    server = fake(tables={"profiles": [PROFILE]}, missing={"businesses"})
    sys.argv = ["sync_to_supabase.py", "--demo"]
    assert sync_to_supabase.main() == 0
    out = capsys.readouterr().out
    assert "sushi  4 sample spots (demo)" in out and "Tamago Sushi (sushi)" in out
    assert "Ruth's migration isn't applied" in out
    profiles_read = server.sent("profiles", "GET")[0]["params"]
    assert profiles_read["account_type"] == "eq.business"
    assert set(profiles_read["select"].split(",")) <= {"user_id", "display_name", "business_name", "business_address", "cuisine"}
    assert len(server.sent("spot_scores")) == 5  # one insert per food type
    assert all(set(r) == SPOT_SCORES for r in server.rows("spot_scores"))
    public = server.rows("alerts")
    assert public and all(set(a) == ALERTS and a["audience"] == "consumer" for a in public)
    assert not server.sent("saved_spots") and not server.sent("profiles")  # the app's own tables are never written
    local = store.business_for_remote(f"profile:{OWNER}")
    assert (local["name"], local["business_type"], local["address"]) == ("Tamago Sushi", "sushi", "1520 E Olive Way, Seattle")


def test_sync_links_ruths_business_when_her_tables_exist(fake, capsys):
    server = fake(tables={"profiles": [PROFILE], "businesses": []})
    sys.argv = ["sync_to_supabase.py", "--skip-scores"]
    assert sync_to_supabase.main() == 0
    created = server.sent("businesses")[0]["body"][0]
    assert created == {"owner_id": OWNER, "name": "Tamago Sushi", "business_type": "sushi", "location": "1520 E Olive Way, Seattle"}
    assert store.business_for_remote(RUTH_BIZ)["name"] == "Tamago Sushi"
    assert "alerts from Ruth's changes: 0" in capsys.readouterr().out


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
    changes = [{"id": "c1", "business_id": RUTH_BIZ, "kind": "price_change", "competitor_name": "Umi Counter",
                "before": "$14", "after": "$16", "why_it_matters": "Your nigiri is now cheaper.", "created_at": "2026-10-25T20:00:00+00:00"},
               {"id": "c2", "business_id": RUTH_BIZ, "kind": "hours_change", "competitor_name": "Umi Counter",
                "before": "9pm", "after": "11pm", "why_it_matters": "", "created_at": "2026-10-25T20:00:00+00:00"}]
    monkeypatch.setattr(store, "remote_changes", lambda remote_id, since: changes if remote_id == RUTH_BIZ else [])
    assert sync_to_supabase.change_alerts(local, RUTH_BIZ) == 3
    rows = server.rows("alerts")
    assert [(r["kind"], r["audience"]) for r in rows] == [("price_change", "business"), ("price_change", "consumer"), ("hours_change", "business")]
    assert "cheaper" in rows[0]["detail"] and "cheaper" not in rows[1]["detail"]  # owner advice stays out of public alerts
    assert len({r["id"] for r in rows}) == 3
