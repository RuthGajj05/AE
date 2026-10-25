# crumbs backend API

Base URL: `http://localhost:8000`. CORS allows the Vite app (`http://localhost:5173`). The frontend only needs
`VITE_API_URL=http://localhost:8000`; every key stays in `backend/.env`.

**Errors** are always `{"error": "plain-English message"}` with a 4xx/5xx status. **Partial data** is not an error:
responses carry `collectionStatus: "partial"` and `caveats` when some sources failed.

**Demo mode**: `DEMO_MODE=1` in the environment, or `?demo=true` on any request, serves fixtures from `backend/demo/`
(made-up spot names, the frontend mock's shapes) flagged `"demo": true`. The stage demo never depends on live
scraping.

## Consumer

### `GET /api/health`

Which keys are set (booleans only, never values), demo mode and the 24h cache.

```json
{ "ok": true, "demo_mode": false, "has_key": true,
  "keys": { "ANTHROPIC_API_KEY": true, "TAVILY_API_KEY": true, "GOOGLE_PLACES_API_KEY": false, "SQUARE_ACCESS_TOKEN": false },
  "squareEnvironment": "sandbox", "scoringModel": "claude-sonnet-5-5",
  "cache": { "areasCached": 5, "areasFresh": 5, "freshCuisines": ["pizza", "ramen", "steak", "sushi", "tacos"],
             "newestScrapedAt": "2026-10-25T21:40:00+00:00", "picks": 30, "demoPicks": 30 } }
```

### `GET /api/cuisines`

```json
[{ "id": "sushi", "label": "Sushi", "pickLine": "good rice and fish, short waits",
   "attributes": [{ "id": "rice", "label": "Rice" }, { "id": "fish", "label": "Fish" }, { "id": "seaweed", "label": "Seaweed" },
                  { "id": "value", "label": "Value" }, { "id": "wait", "label": "Wait time", "unit": "min" }] }]
```

Same five food types, attributes and labels as `frontend/src/crumbs/data/cuisines.json`. Rows with a `unit` are not
Claude scores (wait comes from minutes in reviews). The frontend appends Ambiance itself.

### `GET /api/spots?cuisine=sushi&lat=47.6190&lng=-122.3210&radiusMi=1`

| Param | Default | Notes |
|---|---|---|
| `cuisine` | required | `sushi`, `ramen`, `steak`, `pizza`, `tacos` |
| `lat`, `lng` | Capitol Hill | Center of the search |
| `radiusMi` | `1` | 0.1–5 |
| `depth` | `fast` | `fast` = Ruth's `fast_competitors`; `deep` = `competitor_agent.research` (slower, more review text) |
| `refresh` | `false` | Skip the 24h cache |
| `demo` | `false` | Fixtures |

```json
{
  "cuisine": "sushi",
  "spots": [{
    "id": "sushi-hikari", "name": "Hikari Sushi Bar", "lat": 47.6152, "lng": -122.3185,
    "address": "E Pike St, Seattle, WA", "street": "E Pike St", "price": "$$$", "distanceMi": 0.29,
    "scores": { "rice": 93, "fish": 91, "seaweed": 84, "value": 72 },
    "waitMinutes": 9, "ambiancePct": 81, "ambianceMentionRate": 0.25,
    "bestAt": "Best rice", "reason": "Reviewers keep praising the warm, well-seasoned rice.",
    "reviewCount": 412, "sourceKinds": ["search_snippet", "google_places_sample"], "collectionStatus": "complete",
    "rating": 4.6, "platformReviewCount": 1180, "pick": true
  }],
  "pickId": "sushi-hikari",
  "pickReason": "Highest average review score nearby (88/100, about a 9-min wait). Reviewers keep praising the warm, well-seasoned rice.",
  "areaAverages": { "rice": 80, "fish": 82, "seaweed": 82, "value": 76, "waitMinutes": 11, "ambiancePct": 74 },
  "reviewsRead": 1247,
  "scrapedAt": "2026-10-25T21:40:00+00:00",
  "source": "live",
  "collectionStatus": "complete",
  "caveats": []
}
```

How each value is made:

| Field | Meaning |
|---|---|
| `scores` | One Claude call per spot (`claude-sonnet-5-5`, JSON validated with Pydantic) scores each attribute 0–100 **from review text only**. `null` when no review mentions it — never guessed. |
| `waitMinutes` | Median of the wait times reviewers actually state ("waited 20 minutes", "15–20 min line" → 17.5, "no wait" → 0). `null` if none are stated. Computed in code, not by Claude. |
| `ambiancePct` | Positive ambiance mentions ÷ all ambiance mentions, 0–100. `null` with no mentions. |
| `ambianceMentionRate` | Reviews mentioning ambiance ÷ reviews read, 0–1. |
| `bestAt` | The attribute where this spot is #1 in this list ("Best rice", "Shortest wait", "Best vibe"); `null` if it leads nothing. |
| `reason` | One short line paraphrasing reviewers about `bestAt` (or overall). |
| `reviewCount` | Review texts actually read for this spot (up to 40). `platformReviewCount` is what a listing shows. |
| `sourceKinds` | Ruth's labels: `search_snippet`, `google_places_sample`, `review_text`, `editorial` (`demo` in fixtures). |
| `pick` / `pickId` | crumbs pick = highest average of the 0–100 scores, with wait converted to a 0–100 score (0 min = 100, 30+ min = 0) for ranking only. Ties go to more reviews read. |
| `source` | `live` (just scored), `cache` (≤24h old; `stale: true` if older because a live refresh failed), `demo`. |

A first live call for an area takes a minute or two; run `scripts/prewarm.py` before a demo so it's instant. Two
calls for the same area at once share one run.

### `GET /api/spots/{id}`

Everything above plus `highlights` (one line per attribute), `summary`, `reviews`
(`[{text, sourceKind, sourceUrl, publishedAt}]`), `praisedFor`, `complaints`, `specialties`, `pricePoints`, `sources`,
`website`, `hours`, `scoredAt`, and:

```json
{ "mapsUrl": "https://www.google.com/maps/dir/?api=1&destination=47.6152,-122.3185&travelmode=walking" }
```

Optional `?cuisine=` picks which food type's scores to return when a spot was scored for several.

### `POST /api/picks`

```json
{ "cuisine": "sushi", "chosenSpotId": "sushi-hikari", "comparedSpotIds": ["sushi-hikari", "sushi-umi", "biz-tamago"] }
```
→ `{ "ok": true }`

Stored **anonymously**: cuisine, chosen id, compared ids and a timestamp. No user id, IP, device or any other field
is stored; extra fields in the body are ignored.

## Business

### `GET /api/places/search?q=dicks broadway`

Google Places Autocomplete when `GOOGLE_PLACES_API_KEY` is set, otherwise OpenStreetMap Nominatim; biased to
Capitol Hill.

```json
{ "results": [{ "placeId": "osm:way/206048450", "name": "Dick's Drive-In - Broadway", "address": "115 Broadway East, Seattle",
                "lat": 47.6193, "lng": -122.3212, "source": "osm" }], "source": "osm" }
```

Google results have `lat`/`lng` `null` (filled in on onboarding from the place id).

### `POST /api/business/onboard`

```json
{
  "placeId": "osm:way/206048450",
  "name": "Dick's Drive-In - Broadway", "address": "115 Broadway East, Seattle", "lat": 47.6193, "lng": -122.3212,
  "cuisine": "sushi",
  "goals": ["Shorter waits", "Rice"],
  "questionnaire": { "businessType": "", "location": "", "offerings": "", "customers": "", "currentApproach": "", "constraints": "" },
  "deepResearch": false
}
```
→ `{ "businessId": "biz-3a621cbb88", "status": "queued" }`

Send `placeId` or `name` (+ `address`, and `lat`/`lng` from search when you have them). `questionnaire` uses Manny's
fields from `lib/business-profile.ts`; all optional, blanks dropped. Scoring runs in the background: the area is
scored (or read from the cache), and this business is linked to its spot if discovery found it, otherwise its own
reviews are collected and scored. `deepResearch: true` also runs Ruth's full research for `gap` (several minutes).

### `GET /api/business/{id}/insights`

```json
{
  "businessId": "biz-tamago", "name": "Tamago Sushi", "cuisine": "sushi", "status": "complete", "error": null,
  "demo": true, "period": "last 7 days",
  "reputation": 84, "momentum": 30, "edge": 50,
  "breakdown": [
    { "attribute": "wait", "label": "Wait time", "unit": "min", "you": 18, "areaAvg": 11, "isGoal": true },
    { "attribute": "rice", "label": "Rice", "unit": "pts", "you": 78, "areaAvg": 80, "isGoal": true }
  ],
  "wait": { "youMinutes": 18, "areaMinutes": 11 },
  "ambiance": { "pct": 62, "mentionRate": 0.25 },
  "biggestDrag": { "attribute": "wait", "text": "Your wait is about 7 min longer than the area average (18 vs 11 min)." },
  "gap": null
}
```

| Field | Meaning (all 0–100, `null` when there isn't data yet) |
|---|---|
| `reputation` | Average of your 0–100 review scores |
| `momentum` | Share of the last 7 days' picks you won, among picks where you were compared |
| `edge` | Share of head-to-head attribute comparisons with each nearby spot that you win (ties count half) |
| `breakdown` | Every attribute plus wait and ambiance, the owner's goals first in their order |
| `biggestDrag` | Where you trail the area average most (minutes and points on one scale) |
| `gap` | From Ruth's `market_intelligence.product_gaps` when a deep run produced one, else `null` |

`status` is `queued`, `running`, `complete`, `partial` or `failed` (with `error`). While scoring, the numbers are
`null` and `breakdown` is empty.

### `GET /api/business/{id}/rivals?days=7`

```json
{
  "businessId": "biz-tamago", "days": 7, "demo": true, "status": "complete",
  "picksWon": 9, "picksLost": 21,
  "rivals": [
    { "spotId": "sushi-hikari", "name": "Hikari Sushi Bar", "picksWon": 11,
      "likelyBecause": { "attribute": "wait", "label": "Wait time", "you": 18, "them": 9, "unit": "min", "gapLabel": "+9 min" } },
    { "spotId": "sushi-umi", "name": "Umi Counter", "picksWon": 5,
      "likelyBecause": { "attribute": "ambiance", "label": "Ambiance", "you": 62, "them": 88, "unit": "pts", "gapLabel": "−26 pts" } }
  ],
  "whereYouWin": [{ "attribute": "seaweed", "label": "Seaweed", "you": 94, "bestRival": 92, "unit": "pts", "leadLabel": "+2 pts" }]
}
```

From the picks table: a pick counts when this business was one of `comparedSpotIds`. `likelyBecause` is the
attribute where the rival beats you by the most, with minutes and points on one scale (wait spans 0–30 min, the same
rule as the frontend's `metrics.js`). `whereYouWin` lists attributes where you beat every nearby spot.

The demo business `biz-tamago` has 30 seeded demo picks (flagged `demo` in the table, kept inside the last 7 days).
Demo picks never count for a real business.

## Kneha's endpoints (unchanged)

- `POST /api/recommendations` — owner profile + competitors → ranked tips (`?demo=true` for canned tips).
- `POST /api/analyze`, `GET /api/reports/{id}` — the earlier one-call research.
