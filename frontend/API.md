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
| `competitors[].lat`, `lng` | **New — please add (Ruth).** The map needs them; LocalEdge passes them through |
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
