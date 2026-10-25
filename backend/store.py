"""All database access for the crumbs backend. Nothing else touches SQL.

SQLite now (backend/crumbs.db); swap this one file for Supabase later. The first three tables mirror
Ruth's Supabase schema (supabase/migrations/20261025000000_competitor_monitoring.sql): businesses,
competitors, snapshots. crumbs adds spots, spot_scores, picks and business_goals, plus two caches
(area_cache for 24h scored results, geocodes so an address is only looked up once).

JSON columns are stored as text and decoded on the way out. Picks are anonymous: no user id, no IP,
no device or personal data, only which spots were compared and which one was chosen.
"""

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

_lock = threading.Lock()

SCHEMA = """
create table if not exists businesses (
  id text primary key,
  name text not null,
  business_type text not null,          -- cuisine id for crumbs, e.g. 'sushi'
  location text not null,               -- e.g. 'Capitol Hill, Seattle'
  website text,
  address text,
  lat real,
  lng real,
  place_id text,
  spot_id text,                         -- this business's row in spots
  profile text not null default '{}',   -- Manny's questionnaire answers
  scoring_status text not null default 'queued',  -- queued | running | complete | partial | failed
  scoring_error text,
  demo integer not null default 0,
  created_at text not null,
  updated_at text not null
);

create table if not exists competitors (
  id text primary key,
  business_id text not null references businesses (id) on delete cascade,
  name text not null,
  address text,
  website text,
  rating real,
  review_count integer,
  hours text,
  status text,
  details text not null default '{}',
  first_seen_at text not null,
  last_seen_at text not null,
  unique (business_id, name)
);

create table if not exists snapshots (
  id text primary key,
  business_id text references businesses (id) on delete cascade,  -- null for consumer area runs
  area_key text,
  taken_at text not null,
  data text not null                    -- raw collector output from Ruth's agent
);
create index if not exists snapshots_area_idx on snapshots (area_key, taken_at desc);

create table if not exists spots (
  id text primary key,
  name text not null,
  address text,
  lat real,
  lng real,
  price text,
  website text,
  rating real,
  platform_review_count integer,        -- the count a listing shows, not reviews we read
  hours text,
  details text not null default '{}',   -- praised_for, complaints, specialties, price_points, sources
  reviews text not null default '[]',   -- [{text, source_kind, source_url, published_at}]
  collection_status text not null default 'complete',
  updated_at text not null
);

create table if not exists spot_scores (
  spot_id text not null references spots (id) on delete cascade,
  cuisine text not null,
  scores text not null,                 -- {attribute: 0-100 or null}
  highlights text not null default '{}',-- {attribute: one short line from the reviews}
  summary text,
  wait_minutes real,
  ambiance_pct integer,
  ambiance_mention_rate real,
  review_count integer not null default 0,
  source_kinds text not null default '[]',
  model text,
  scored_at text not null,
  primary key (spot_id, cuisine)
);

create table if not exists area_cache (
  area_key text primary key,
  cuisine text not null,
  lat real not null,
  lng real not null,
  radius_mi real not null,
  payload text not null,
  collection_status text not null,
  scraped_at text not null
);

create table if not exists geocodes (
  address text primary key,
  lat real,
  lng real,
  source text,
  created_at text not null
);

create table if not exists picks (
  id integer primary key autoincrement,
  cuisine text not null,
  chosen_spot_id text not null,
  compared_spot_ids text not null,
  created_at text not null,
  demo integer not null default 0
);
create index if not exists picks_cuisine_idx on picks (cuisine, created_at);

create table if not exists business_goals (
  business_id text not null references businesses (id) on delete cascade,
  goal text not null,
  position integer not null,
  primary key (business_id, goal)
);
"""

_JSON_COLUMNS = {"profile", "details", "reviews", "scores", "highlights", "source_kinds", "payload", "compared_spot_ids", "data"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _db():
    path = Path(config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for key in _JSON_COLUMNS & out.keys():
        if isinstance(out[key], str):
            out[key] = json.loads(out[key])
    return out


def _dump(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def init() -> None:
    with _db() as db:
        db.executescript(SCHEMA)


# ---------- businesses ----------

def create_business(*, name: str, business_type: str, location: str, address: str | None = None,
                    lat: float | None = None, lng: float | None = None, place_id: str | None = None,
                    website: str | None = None, profile: dict | None = None, business_id: str | None = None,
                    demo: bool = False) -> str:
    business_id = business_id or f"biz-{uuid.uuid4().hex[:10]}"
    stamp = now()
    with _db() as db:
        db.execute(
            "insert or replace into businesses (id, name, business_type, location, website, address, lat, lng, place_id,"
            " spot_id, profile, scoring_status, demo, created_at, updated_at)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)",
            (business_id, name, business_type, location, website, address, lat, lng, place_id,
             f"spot-{business_id}", _dump(profile or {}), int(demo), stamp, stamp),
        )
    return business_id


def get_business(business_id: str) -> dict | None:
    with _db() as db:
        return _row(db.execute("select * from businesses where id = ?", (business_id,)).fetchone())


def update_business(business_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = [_dump(v) if k in _JSON_COLUMNS else v for k, v in fields.items()]
    with _db() as db:
        db.execute(f"update businesses set {cols} where id = ?", (*values, business_id))


def set_goals(business_id: str, goals: list[str]) -> None:
    with _db() as db:
        db.execute("delete from business_goals where business_id = ?", (business_id,))
        db.executemany(
            "insert or ignore into business_goals (business_id, goal, position) values (?, ?, ?)",
            [(business_id, g, i) for i, g in enumerate(goals)],
        )


def get_goals(business_id: str) -> list[str]:
    with _db() as db:
        rows = db.execute("select goal from business_goals where business_id = ? order by position", (business_id,)).fetchall()
    return [r["goal"] for r in rows]


# ---------- competitors and snapshots (Ruth's tables) ----------

def upsert_competitors(business_id: str, competitors: list[dict]) -> None:
    stamp = now()
    with _db() as db:
        for c in competitors:
            db.execute(
                "insert into competitors (id, business_id, name, address, website, rating, review_count, hours, status,"
                " details, first_seen_at, last_seen_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " on conflict (business_id, name) do update set address = excluded.address, website = excluded.website,"
                " rating = excluded.rating, review_count = excluded.review_count, hours = excluded.hours,"
                " status = excluded.status, details = excluded.details, last_seen_at = excluded.last_seen_at",
                (uuid.uuid4().hex, business_id, c["name"], c.get("address"), c.get("website"), c.get("rating"),
                 c.get("review_count"), c.get("hours"), c.get("status"), _dump(c), stamp, stamp),
            )


def save_snapshot(data: dict, *, business_id: str | None = None, area_key: str | None = None) -> str:
    snapshot_id = uuid.uuid4().hex
    with _db() as db:
        db.execute("insert into snapshots (id, business_id, area_key, taken_at, data) values (?, ?, ?, ?, ?)",
                   (snapshot_id, business_id, area_key, now(), _dump(data)))
    return snapshot_id


# ---------- spots and scores ----------

def upsert_spot(spot: dict) -> None:
    with _db() as db:
        db.execute(
            "insert or replace into spots (id, name, address, lat, lng, price, website, rating, platform_review_count,"
            " hours, details, reviews, collection_status, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (spot["id"], spot["name"], spot.get("address"), spot.get("lat"), spot.get("lng"), spot.get("price"),
             spot.get("website"), spot.get("rating"), spot.get("platform_review_count"), spot.get("hours"),
             _dump(spot.get("details") or {}), _dump(spot.get("reviews") or []),
             spot.get("collection_status", "complete"), now()),
        )


def get_spot(spot_id: str) -> dict | None:
    with _db() as db:
        return _row(db.execute("select * from spots where id = ?", (spot_id,)).fetchone())


def save_score(spot_id: str, cuisine: str, score: dict) -> None:
    with _db() as db:
        db.execute(
            "insert or replace into spot_scores (spot_id, cuisine, scores, highlights, summary, wait_minutes, ambiance_pct,"
            " ambiance_mention_rate, review_count, source_kinds, model, scored_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (spot_id, cuisine, _dump(score["scores"]), _dump(score.get("highlights") or {}), score.get("summary"),
             score.get("waitMinutes"), score.get("ambiancePct"), score.get("ambianceMentionRate"),
             score.get("reviewCount", 0), _dump(score.get("sourceKinds") or []), score.get("model"), now()),
        )


def get_score(spot_id: str, cuisine: str) -> dict | None:
    with _db() as db:
        return _row(db.execute("select * from spot_scores where spot_id = ? and cuisine = ?", (spot_id, cuisine)).fetchone())


# ---------- 24h area cache ----------

def get_area(area_key: str, max_age_hours: float = config.CACHE_HOURS) -> dict | None:
    with _db() as db:
        row = _row(db.execute("select * from area_cache where area_key = ?", (area_key,)).fetchone())
    if not row:
        return None
    age = datetime.now(timezone.utc) - datetime.fromisoformat(row["scraped_at"])
    return row if age <= timedelta(hours=max_age_hours) else None


def put_area(area_key: str, *, cuisine: str, lat: float, lng: float, radius_mi: float, payload: dict, status: str) -> None:
    with _db() as db:
        db.execute(
            "insert or replace into area_cache (area_key, cuisine, lat, lng, radius_mi, payload, collection_status, scraped_at)"
            " values (?, ?, ?, ?, ?, ?, ?, ?)",
            (area_key, cuisine, lat, lng, radius_mi, _dump(payload), status, payload.get("scrapedAt") or now()),
        )


def cache_stats() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=config.CACHE_HOURS)).isoformat(timespec="seconds")
    with _db() as db:
        rows = db.execute("select cuisine, scraped_at from area_cache order by scraped_at desc").fetchall()
        picks = db.execute("select count(*) as n, coalesce(sum(demo), 0) as demo from picks").fetchone()
    fresh = [r for r in rows if r["scraped_at"] >= cutoff]
    return {
        "areasCached": len(rows),
        "areasFresh": len(fresh),
        "freshCuisines": sorted({r["cuisine"] for r in fresh}),
        "newestScrapedAt": rows[0]["scraped_at"] if rows else None,
        "picks": picks["n"],
        "demoPicks": picks["demo"],
    }


# ---------- geocodes ----------

def _address_key(address: str) -> str:
    return " ".join(address.lower().split())


def get_geocode(address: str) -> dict | None:
    with _db() as db:
        return _row(db.execute("select * from geocodes where address = ?", (_address_key(address),)).fetchone())


def put_geocode(address: str, lat: float | None, lng: float | None, source: str) -> None:
    with _db() as db:
        db.execute("insert or replace into geocodes (address, lat, lng, source, created_at) values (?, ?, ?, ?, ?)",
                   (_address_key(address), lat, lng, source, now()))


# ---------- picks (anonymous) ----------

def add_pick(cuisine: str, chosen_spot_id: str, compared_spot_ids: list[str], *, demo: bool = False,
             created_at: str | None = None) -> None:
    with _db() as db:
        db.execute("insert into picks (cuisine, chosen_spot_id, compared_spot_ids, created_at, demo) values (?, ?, ?, ?, ?)",
                   (cuisine, chosen_spot_id, _dump(compared_spot_ids), created_at or now(), int(demo)))


def picks_since(cuisine: str, since: datetime, *, include_demo: bool) -> list[dict]:
    query = "select * from picks where cuisine = ? and created_at >= ?" + ("" if include_demo else " and demo = 0")
    with _db() as db:
        rows = db.execute(query + " order by created_at", (cuisine, since.isoformat(timespec="seconds"))).fetchall()
    return [_row(r) for r in rows]


def count_demo_picks(cuisine: str) -> int:
    with _db() as db:
        return db.execute("select count(*) from picks where cuisine = ? and demo = 1", (cuisine,)).fetchone()[0]


def clear_demo_picks(cuisine: str) -> None:
    with _db() as db:
        db.execute("delete from picks where cuisine = ? and demo = 1", (cuisine,))
