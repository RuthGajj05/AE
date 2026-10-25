# Backend

FastAPI service for crumbs and Kneha's recommendations API. Keys stay here; the frontend never sees them.
crumbs contract: [API.md](API.md).

## Run

Needs Python 3.10+ (Ruth's agent uses 3.10 syntax). If `python3 --version` is older, install 3.12 from
python.org, or with uv: `pip3 install --user uv && uv python install 3.12`.

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then add ANTHROPIC_API_KEY and TAVILY_API_KEY (GOOGLE_PLACES_API_KEY optional)
.venv/bin/uvicorn main:app --reload --port 8000
```

`backend/.env` is loaded automatically (no `export` needed). Check it at http://localhost:8000/api/health: it shows
which keys are set (true/false only) and what's cached.

### Before a demo: prewarm

Scores all five food types for Capitol Hill (lat 47.6190, lng -122.3210, 1 mi) and caches them for 24 hours so the
app loads instantly. Takes a minute or two per food type.

```sh
.venv/bin/python scripts/prewarm.py              # skips anything still fresh
.venv/bin/python scripts/prewarm.py --refresh    # re-score everything
```

### Demo mode (no live calls at all)

```sh
DEMO_MODE=1 .venv/bin/uvicorn main:app --port 8000
```

Or add `?demo=true` to any request. Serves `backend/demo/` (made-up spots in the frontend mock's shapes); the demo
business `biz-tamago` has 30 seeded demo picks for the Rivals screen. Rebuild the fixtures from the frontend mock
with `.venv/bin/python scripts/build_demo_fixtures.py ../frontend/src/crumbs/data`.

### Alerts on a schedule

```sh
.venv/bin/python scripts/check_alerts.py --all --stock-only   # Square stock: hourly (needs SQUARE_ACCESS_TOKEN)
.venv/bin/python scripts/check_alerts.py --all                # plus Ruth's competitor monitor: a few times a week
```

The first monitor run per business saves a baseline. `top_rated` alerts come from re-scoring areas
(`scripts/prewarm.py --refresh`). See API.md → Alerts.

### Tests

```sh
.venv/bin/python -m pytest tests -q
```

These cover:
- the scoring math (wait median, ambiance, pick, rival gaps) on fixture reviews
- every endpoint in demo mode
- the live path, with the collector and Claude replaced by fakes
- the exact Claude request shape, against a mock transport

The tests make no network calls.

## How it fits together

| File | What it does |
|---|---|
| `main.py` | Kneha's app: CORS, error handlers, `/api/recommendations`; mounts the crumbs router |
| `crumbs_api.py` | crumbs endpoints |
| `pipeline.py` | Collect → score → cache, business onboarding (background), insights, rivals |
| `collect.py` | Drives Ruth's agent (`agent/`): `fast_competitors` by default, `competitor_agent.research` with `depth=deep` |
| `reviewer.py` | One `claude-sonnet-5-5` call per spot: 0–100 attribute scores from review text, validated with Pydantic |
| `scoring.py` | Pure math: wait median, ambiance, pick, best-at, rival gaps, insights |
| `store.py` | **All** database access (SQLite now, `crumbs.db`; swap this one file for Supabase later) |
| `geo.py` | Census geocoder + Nominatim; Google Places or OSM place search |
| `alerts.py` | Alerts: Ruth's monitor (via a SQLite adapter, or her Supabase store), Square stock, top-rated |
| `square_inventory.py` | Square IN_STOCK counts, a port of Manny's `lib/square.ts` |
| `demo.py`, `demo/` | Demo fixtures and seeded demo picks |
| `config.py` | Loads `backend/.env`; settings |

Tables mirror Ruth's Supabase schema (`businesses`, `competitors`, `snapshots`, `monitor_runs`, `changes`) plus
`spots`, `spot_scores`, `picks`, `business_goals`, `alerts`, `alert_reads`, `inventory_snapshots`, and caches for scored
areas and geocodes.

## Endpoints

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/health`, `GET /api/cuisines` | done | |
| `GET /api/spots`, `GET /api/spots/{id}`, `POST /api/picks` | done | Live scoring needs keys; demo works without |
| `GET /api/places/search`, `POST /api/business/onboard` | done | |
| `GET /api/business/{id}/insights`, `GET /api/business/{id}/rivals` | done | |
| `GET /api/alerts`, `POST /api/alerts/{id}/read`, `POST /api/business/{id}/alerts/refresh` | done | Demo works without keys |
| `POST /api/recommendations` | done | Kneha's, unchanged. Contract in `frontend/API.md`. `?demo=true` returns canned tips. |
| `GET /api/competitors` | not built | LocalEdge's old two-endpoint contract; crumbs uses `/api/spots` instead. |
| `POST /api/analyze` | extra | Earlier one-call version (search + report). Not used by the frontend. |

Errors are returned as `{"error": "plain-English message"}`.
