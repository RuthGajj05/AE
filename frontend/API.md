# LocalEdge API contract

What the frontend sends and expects back. There are two endpoints, so scraping and the Claude tips can be built
separately:

| Endpoint | Owner | What it does |
|---|---|---|
| `GET /api/competitors` | scraping | Finds nearby competitors and their prices, waits, ratings and review complaints |
| `POST /api/recommendations` | Claude | Turns the owner's profile + those competitors into ranked tips |

The frontend calls competitors first, shows that data right away, then calls recommendations with the competitors
it just got back.

The TypeScript version of every shape is in `src/types.ts`. All calls go through `src/api/client.ts`, and
`src/api/mock.ts` shows working example responses.

## Connecting the frontend to your backend

1. Run your server (any port, e.g. `http://localhost:8000`).
2. Allow the frontend's origin with CORS (dev: `http://localhost:5173`). `GET`, `POST` and the `Content-Type` header
   are enough.
   - Express: `app.use(require('cors')())`
   - FastAPI: `app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])`
3. In `frontend/`, copy `.env.example` to `.env.local` and set `VITE_API_URL=http://localhost:8000`, then restart
   `npm run dev`.

Without `VITE_API_URL` the frontend uses mock data. Adding `?mock` to the page URL forces mock data even when a
backend is set — the demo fallback if the backend has trouble.

**Keys stay on the backend.** The frontend never sees a Claude or scraping key, and `.env.local` must only hold
the URL. Anything named `VITE_*` is shipped to the browser.

---

## `GET /api/competitors`

### Request

Query parameters (all always sent):

| Param | Example | Notes |
|---|---|---|
| `category` | `bakery` | One of `bakery`, `coffee`, `tacos`, `pho` |
| `item` | `butter croissant` | The benchmark item to find prices for. bakery → `butter croissant`, coffee → `12 oz latte`, tacos → `al pastor taco`, pho → `large beef pho` |
| `neighborhood` | `beacon-hill` | Owner's neighborhood id |
| `lat`, `lng` | `47.579`, `-122.3115` | Center of that neighborhood; search around this point |
| `radiusMi` | `4` | Search radius in miles: `2`, `4`, or `15` (all Seattle) |

```
GET /api/competitors?category=bakery&item=butter+croissant&neighborhood=beacon-hill&lat=47.579&lng=-122.3115&radiusMi=4
```

### Response `200`

```json
{
  "source": "live",
  "scrapedAt": "2026-10-25T19:21:00Z",
  "trends": [
    "Searches for “matcha croissant” in Seattle are up 41% over the last 90 days."
  ],
  "competitors": [
    {
      "id": "golden-crumb-bakehouse",
      "name": "Golden Crumb Bakehouse",
      "neighborhood": "Capitol Hill",
      "distanceMi": 3.2,
      "rating": 4.6,
      "reviewCount": 812,
      "itemPrice": 5.25,
      "waitMin": 9,
      "priceChange90d": 4,
      "complaints": { "wait": 31, "price": 12, "seating": 9 },
      "url": "https://example.com/golden-crumb"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `source` | `"live"` or `"sample"` | Use `"sample"` if you're returning canned data; the UI labels it |
| `scrapedAt` | ISO 8601 string | Shown as "Live · 12:21 PM" |
| `trends` | string[] | 0–3 short, plain-English sentences. Empty array is fine |
| `competitors` | array | Empty array is fine; the UI shows "none found" |
| `id` | string | Anything stable and unique |
| `name` | string | **Required.** Rows without a name are skipped |
| `neighborhood` | string | Display name, e.g. `"Capitol Hill"` |
| `distanceMi` | number \| null | Miles from `lat`/`lng`. The table is sorted by this |
| `rating` | number \| null | 1–5 |
| `reviewCount` | number \| null | |
| `itemPrice` | number \| null | Dollars for the `item` requested, e.g. `5.25` |
| `waitMin` | number \| null | Typical minutes from ordering to food in hand |
| `priceChange90d` | number \| null | Percent, e.g. `4` = +4%, `-2` = −2% |
| `complaints` | object | Review-mention counts per theme key below. Unknown keys are ignored |
| `url` | string, optional | Listing or website. Only `http(s)://` links are shown |

**Missing data is fine — send `null`, don't guess.** If the scraper can't find a price or wait time, send `null`.
The UI shows "—" and leaves it out of medians and charts. The frontend also accepts numbers as strings
(`"$5.10"`, `"1,204"`, `"3%"`), but real numbers are better.

### Complaint theme keys

Tag each review with zero or more of these, then count per competitor:

| Key | Meaning |
|---|---|
| `wait` | Long waits / slow service |
| `price` | Too expensive |
| `portions` | Small portions |
| `service` | Rude or unfriendly staff |
| `hours` | Closes too early / limited hours |
| `online` | No online ordering or delivery |
| `consistency` | Quality varies visit to visit |
| `seating` | Nowhere to sit |

---

## `POST /api/recommendations`

### Request

`Content-Type: application/json`

```json
{
  "profile": {
    "name": "Rise & Knead Bakery",
    "category": "bakery",
    "neighborhood": "beacon-hill",
    "reviewUrl": "https://g.page/r/your-business/review",
    "rating": 4.5,
    "reviewCount": 142,
    "itemPrice": 4.25,
    "waitMin": 6
  },
  "competitors": [ /* exactly what /api/competitors returned, after cleanup */ ]
}
```

`reviewUrl` may be an empty string. `itemPrice` is the owner's price for the same benchmark item.

### Response `200`

```json
{
  "recommendations": [
    {
      "id": "price-low",
      "title": "You have room to raise your butter croissant price",
      "evidence": "Yours is $4.25; the median nearby is $4.75 (-11%). 2 of 4 competitors raised prices in the last 90 days.",
      "action": "Try $4.60 for two weeks and watch your daily count. You would still be below the area median.",
      "impact": "high",
      "effort": "low"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | Unique within the response |
| `title` | string | **Required.** One line, plain English |
| `evidence` | string | The real numbers behind the tip. This is what makes it trustworthy — always cite numbers from the data |
| `action` | string | One concrete thing to try this week |
| `impact` | `"high"` \| `"medium"` \| `"low"` | Anything else shows as medium |
| `effort` | `"high"` \| `"medium"` \| `"low"` | Anything else shows as medium |

Send 3–6 tips. The frontend shows them in the order you send, so rank them (high impact, low effort first).

**Prompting tips for the Claude call:** ask for JSON matching this shape only. Tell Claude to use only numbers
present in the request, to write for a busy owner who isn't technical, and to avoid promising specific savings or
revenue — the evidence line carries the numbers. `src/api/mock.ts` has rule-based tips showing the tone we want.

---

## Errors and timing

- On failure, return a non-2xx status with `{ "error": "Plain-English message" }`. The message is shown to the user
  with a **Try again** button (and **Use sample data** for competitors).
- The frontend waits up to **90 seconds** per call and shows progress steps while it waits. If scraping takes
  longer, cache results per `category` + `neighborhood` + `radiusMi` so the demo is instant on the second load.
