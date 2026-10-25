# LocalEdge data format

**One format: Ruth's scraper report** (`examples/capitol-hill-bakery-report.json` on the `scraping` branch). The
map and LocalEdge both read it. A copy is bundled at `src/data/capitol-hill-bakery-report.json` and is what the demo
shows.

## Fields the dashboard uses

```json
{
  "business": "Test Bakery",
  "type": "bakery",
  "location": "Capitol Hill, Seattle",
  "date": "2026-10-25",
  "market_summary": "Capitol Hill has a lot of bakeries…",
  "competitors": [
    {
      "name": "The French Guys",
      "address": "810 E Roy St, Seattle, WA 98102",
      "distance_note": "~290 m, the closest bakery (OSM)",
      "lat": 47.6253,
      "lng": -122.3213,
      "website": "https://www.thefrenchguys.com",
      "rating": 4.4,
      "review_count": 185,
      "specialties": ["Croissants (almond, hazelnut, raspberry-filled)"],
      "price_points": ["Almond croissant: $6 (Yelp review)"],
      "praised_for": ["Croissants called amazing and flaky"],
      "complaints": ["Waits can be long, especially when ordering coffee (TripAdvisor)"],
      "sources": ["https://www.yelp.com/biz/the-french-guys-seattle"]
    }
  ],
  "price_benchmarks": ["Plain butter croissant: $3.50–$6.25 (3 shops: Bakery Nouveau $3.50, …)"],
  "insights": [{ "recommendation": "Don't try to win on croissant price. …", "evidence": "Plain croissants range from …" }],
  "gaps_and_caveats": ["Bakery Nouveau: Yelp snippets showed the review count … but no star rating."]
}
```

| Field | Used for |
|---|---|
| `business`, `type`, `location`, `date` | Page header |
| `market_summary` | "Market summary" card |
| `competitors[].distance_note` | Distance column — `"~630 m"`, `"~0.6 mi east"` and `"~1.5 km"` are all parsed |
| `competitors[].lat`, `lng` | **Optional (Ruth).** Used for map pins when present. Until then, pins come from `data/spots.geo.json`, geocoded once from `address` |
| `competitors[].address` | Map card, geocoding, and the zip used by the Seattle license check — keep the zip in it |
| `competitors[].rating`, `review_count` | Rating column and "Market at a glance" tiles. `null` is fine |
| `competitors[].price_points` | "Items from" column (lowest `$` price) and the expanded row |
| `competitors[].complaints` | Top weakness, and grouped into the "What customers complain about" themes |
| `competitors[].specialties`, `praised_for`, `sources`, `website`, `address` | Expanded row (tap a competitor) |
| `price_benchmarks` | "What things cost nearby" range chart — keep the `Item: $min–$max (note)` pattern |
| `insights` | "Claude's suggestions" — first sentence of `recommendation` is the headline, `evidence` is behind "Why" |
| `gaps_and_caveats` | "What we couldn't verify" |

### Optional fields that would improve the demo

- `insights[].impact`: `"high"`, `"medium"` or `"low"` shows an impact badge. Without it, no badge is shown (we
  don't guess).
- `insights[].title`: a short headline. Otherwise the first sentence of `recommendation` is used.
- Owner numbers, e.g. `"business": { "name": "…", "rating": 4.3, "avg_price": 4.25, "avg_wait_minutes": 6 }`. With
  these, "The market at a glance" becomes "You vs nearby" with green/red comparisons.
- `complaint_themes: [{ "theme": "Long waits", "shops": 4, "quote": "…" }]`. Otherwise the frontend groups the
  free-text `complaints` itself with simple keyword matching.

Missing or `null` values are fine everywhere — the UI shows "—" or hides that piece. Rows without a `name` are skipped.
The adapter (`src/data/adapter.js`) also accepts the backend's `{ profile, report }` wrapper and snake_case or
camelCase names.

## Getting the report to the frontend

1. **Demo default:** the bundled saved report. Instant and works offline.
2. **Drag a report JSON onto the page** (or **Load JSON**) to show a fresh run.
3. **Backend (Neha):** `GET /api/report` returns the latest saved report in this format. Then set
   `DATA_URL = 'http://localhost:8000/api/report'` in `src/config.js`. If it fails, the page offers
   "Use saved report" — it never switches silently.

No API keys in the frontend or the repo. They stay with the scraper and backend.

## crumbs map

`src/crumbs/places.js` is the only file that loads data for the crumbs map. Every place has this shape, whether it
comes from Google Places (New) Nearby Search or the sample file:

```json
{
  "id": "ChIJ…",
  "name": "Dick's Drive-In",
  "cuisine": "Hamburger Restaurant",
  "priceLevel": "INEXPENSIVE",
  "rating": 4.5,
  "ratingCount": 4800,
  "address": "115 Broadway E, Seattle",
  "lat": 47.6194,
  "lng": -122.3212
}
```

`priceLevel` is Google's enum (`FREE`, `INEXPENSIVE`, `MODERATE`, `EXPENSIVE`, `VERY_EXPENSIVE`) or `null`.
`rating`, `ratingCount` and `address` can be `null`/empty.

### Proposed: review scores (backend, not built yet)

The card's Freshness / Value / Service chips call `getPlaceScores(placeId)`, which returns all `null` for now.
Proposed endpoint for the backend team (Claude reads the reviews server-side; no Claude calls in the browser):

`GET /api/places/{placeId}/scores` →

```json
{ "placeId": "ChIJ…", "freshness": 8.4, "value": 7.1, "service": 6.9 }
```

Scores 0–10, any of them `null` when there isn't enough review evidence. The chips show `null` as "—".

### Food types: compare data (sample now, backend later)

The food chips (Sushi, Ramen, Steak, Pizza, Tacos) load one food type with `getCuisine(id)` in
`src/crumbs/places.js`. Today it reads `src/crumbs/data/cuisines.json` (made-up spot names, labeled "sample data"
in the app). Proposed endpoint for when Claude scores the reviews server-side:

`GET /api/cuisines/{id}` →

```json
{
  "id": "sushi",
  "label": "Sushi",
  "pickLine": "good rice and fish, short waits",
  "attributes": [{ "id": "rice", "label": "Rice" }, { "id": "wait", "label": "Wait time", "unit": "min" }],
  "spots": [
    {
      "id": "sushi-hikari",
      "name": "Hikari Sushi Bar",
      "lat": 47.6152,
      "lng": -122.3185,
      "price": "$$$",
      "street": "E Pike St",
      "openUntil": "10 PM",
      "phone": "(206) 555-0101",
      "reviewCount": 412,
      "pick": true,
      "scores": { "rice": 93 },
      "waitMinutes": 9,
      "ambiancePct": 81,
      "ambianceMentionRate": 0.25,
      "bestAt": "Best rice",
      "reason": "Reviewers keep praising the warm, well-seasoned rice."
    }
  ]
}
```

- Exactly 4 spots, in the order they should be lettered A–D.
- `scores`: one 0–100 number per attribute without a `unit` (higher is better). `overall` = their average.
- `waitMinutes`: average wait in minutes (shorter is better). Every spot needs it; the "Wait time" row only shows
  for food types that list `{ "id": "wait", "unit": "min" }` in `attributes`.
- `ambiancePct`: % of reviews mentioning the vibe/atmosphere that are positive. `ambianceMentionRate`: share of
  reviews that mention it (0.25 → "in 1 of 4 reviews"). The frontend adds the Ambiance row to every food type.
- `pick: true` on one spot: the best `overall`. The frontend works out letters, walking distance from the user and
  the "reviews read" total (sum of `reviewCount`).
- `bestAt` is a 2–3 word badge, `reason` is one short sentence from the reviews, `pickLine` is a few words for the
  crumbs pick row.

### Pick events

Tapping **Go here** saves an anonymous pick with `recordPick()` (`places.js`). Today it goes to this browser's
`localStorage` (`crumbs.picks`); proposed `POST /api/picks` with the same body. No user info.

```json
{ "cuisine": "sushi", "chosenSpotId": "sushi-hikari", "comparedSpotIds": ["sushi-hikari", "sushi-umi", "sushi-nori-house", "sushi-pike-roll"], "timestamp": "2026-10-25T21:40:46.404Z" }
```

### Business report (Home tab: Insights + Rivals)

`getBusinessReport()` builds it from `src/crumbs/data/business.json` (a made-up shop, Tamago Sushi), the sushi
sample data and this browser's pick events: each local sushi pick counts as a pick lost to the chosen spot.
`src/crumbs/businessReport.js` does the math the backend would: the rival's biggest gap ("likely because of"), the
biggest drag vs the area average, and where you're #1. Proposed `GET /api/business/{id}/report?days=7` →

```json
{
  "you": { "id": "biz-tamago", "name": "Tamago Sushi", "cuisine": "sushi", "scores": { "rice": 78 }, "waitMinutes": 18, "ambiancePct": 62, "ambianceMentionRate": 0.25 },
  "period": "last 7 days",
  "area": "Capitol Hill",
  "picksWon": 9,
  "picksLostTo": { "sushi-hikari": 8, "sushi-umi": 3 }
}
```

The backend only needs to send those counts plus the cuisine data above; gaps and wording are worked out in the app.

### Alerts (Alerts tab)

The frontend follows the backend's contract (`backend/API.md` → Alerts on the `crumbs-backend` branch):

- `GET /api/alerts?audience=consumer&lat=&lng=&radiusMi=1` for everyone; business accounts also call
  `GET /api/alerts?audience=business&businessId=biz-tamago` (the sample shop until onboarding registers the business
  with `POST /api/business`). The two lists are merged, newest first.
- A list that comes back empty is asked again with `demo=true`, and the feed shows "sample data". If the backend is
  down, `src/crumbs/data/alerts.json` is used (same fields; times are shifted so the newest is 12 minutes old).
- Tapping an alert calls `POST /api/alerts/{id}/read` and keeps a copy in `localStorage` (`crumbs.alertsRead`),
  since consumer read flags are shared on the backend.
- Fields used: `id, kind, audience, spotId, cuisine, title, detail, createdAt, read` (`demo` marks sample alerts).
  `spotId` + `cuisine` open that spot's Go here sheet; `spotId: null` opens the food type.

### Sign-in (business owners)

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` in `frontend/.env.local` (see `.env.example`; the
publishable key is safe in the browser, never the secret key). Then "I run a spot" asks for an email + password
first (`src/crumbs/SignIn.jsx`, Supabase Auth via `src/crumbs/auth.js`). Signed in, every backend call carries
`Authorization: Bearer <access token>`; `GET /api/me` restores the owner's spot on a new device; the You tab shows
the email and Sign out (which also switches the account back to Member). Browsing never needs a sign-in. Without
the two variables, sign-in is off and the app behaves as before.

In the Supabase dashboard, set **Authentication → URL Configuration → Site URL** to the app's address (e.g.
`http://localhost:5173`) so the email-confirmation link opens the app.

### Local-only (no backend yet)

`localStorage` keys: `crumbs.account` (Member/Business, profile, favorite foods, alert settings, the business's spot),
`crumbs.saved` + `crumbs.savedSpots` (Saved tab), `crumbs.picks` (Go here picks, also sent to `POST /api/picks`).
