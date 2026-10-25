# LocalEdge data format

The dashboard renders **one JSON document**. The scraper/backend can serve it from a URL or save it as a file —
both work. `src/data/sample.json` is a complete working example.

## The shape

```json
{
  "source": "live",
  "generatedAt": "2026-10-25T19:20:00Z",
  "business": {
    "name": "Rise & Knead Bakery",
    "type": "Bakery",
    "area": "Beacon Hill, Seattle",
    "rating": 4.3,
    "reviewCount": 142,
    "avgPrice": 4.25,
    "waitMin": 6
  },
  "competitors": [
    {
      "name": "Golden Crumb Bakehouse",
      "distanceMi": 3.2,
      "rating": 4.6,
      "reviewCount": 812,
      "avgPrice": 5.25,
      "waitMin": 9,
      "topWeakness": "Long waits",
      "url": "https://example.com/golden-crumb"
    }
  ],
  "reviewThemes": [
    { "theme": "Long waits", "mentions": 57, "quote": "Twenty-minute line for one croissant on a Saturday." }
  ],
  "suggestions": [
    {
      "title": "Advertise how fast you are",
      "why": "57 reviews of nearby bakeries complain about waits. Yours is about 6 min, versus 9 min on average nearby.",
      "impact": "high"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `source` | `"live"` or `"sample"` | Shown as a badge in the top bar |
| `generatedAt` | ISO 8601 string | Shown as "Updated …" and "Live · 12:20 PM" |
| `business.name` | string | The owner's business |
| `business.type` | string | e.g. "Bakery", "Coffee shop" |
| `business.area` | string | e.g. "Beacon Hill, Seattle" |
| `business.rating` | number | 0–5 |
| `business.reviewCount` | number | |
| `business.avgPrice` | number | Dollars, average item price |
| `business.waitMin` | number | Typical minutes from ordering to food in hand |
| `competitors[]` | array | Nearby businesses; sorted by distance in the UI |
| `competitors[].distanceMi` | number | Miles from the business |
| `competitors[].avgPrice`, `waitMin`, `rating`, `reviewCount` | number | Same meaning as for `business` |
| `competitors[].topWeakness` | string | Their most common review complaint |
| `competitors[].url` | string, optional | Only `http(s)://` links are shown |
| `reviewThemes[]` | array | Complaints across competitors' reviews; sorted by `mentions` in the UI |
| `reviewThemes[].quote` | string, optional | One short real review snippet |
| `suggestions[]` | array | Claude's tips, shown in the order sent — put the best first |
| `suggestions[].impact` | `"high"` \| `"medium"` \| `"low"` | Anything else shows as medium |

The "You vs nearby" cards compare `business` against the **average** of the competitors' values.

## Missing or messy data is fine

`src/data/adapter.js` cleans everything up before the UI sees it:

- **Missing values:** send `null` or leave the field out. The UI shows "—" and skips it in averages. Never guess
  a number.
- **Other names work:** `avg_price`, `price`, `itemPrice`; `wait_time`, `wait`; `distance`; `stars`; `reviews`;
  `restaurant` or `you` instead of `business`; `results` or `nearby` instead of `competitors`; `recommendations`
  or `tips` instead of `suggestions`; snake_case anywhere.
- **Strings are parsed:** `"$5.10"`, `"1,204"`, `"4.5 stars"`, `"8-12 min"` (the midpoint), `"650 m"`, `"2 km"`.
- **No `reviewThemes`?** They're added up from each competitor's `complaints` object, e.g.
  `"complaints": { "Long waits": 12, "Rude staff": 4 }`. That object also fills `topWeakness` if it's missing.
- Rows without a name are dropped.

If the scraper's output looks different from all of this, it's a one-line change in `adapter.js`.

## How to hand data to the frontend

Pick whichever is ready first:

1. **Drag the JSON file onto the page** (or click **Load JSON**). No setup, and great for the demo.
2. **A file in the repo:** save it as `frontend/public/scraper-output.json`, then in `frontend/src/config.js` set
   `DATA_URL = '/scraper-output.json'`.
3. **A backend URL:** set `DATA_URL = 'http://localhost:8000/api/dashboard'`. The endpoint must answer `GET` with
   this JSON and allow CORS from the frontend (dev: `http://localhost:5173`).
   - Express: `app.use(require('cors')())`
   - FastAPI: `app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])`

**No API keys in the frontend or the repo.** Claude and scraping keys stay on the backend; the frontend only ever
sees the finished JSON.

## Prompting tip for the Claude suggestions

Ask Claude for JSON matching `suggestions[]` only. Tell it to cite numbers from the scraped data in `why`, write
for a busy owner who isn't technical, and never promise specific savings or revenue.
