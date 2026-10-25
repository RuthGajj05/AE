# LocalEdge — frontend

Competitor insights for small food businesses in Seattle. One page reads a scraper report (Ruth's format) and shows
the market at a glance, who the nearby competitors are, what their customers complain about, what things cost, and
Claude's suggestions, with sources and caveats.

Two views from the same report: **Dashboard** and **Map** (`#/map`), an Airbnb-style list of spot cards beside a
Leaflet map with price pins. Each card checks the shop against Seattle's business license records.

Vite + React + plain CSS + Leaflet (free OpenStreetMap tiles). No login, no API keys.

## Run it

```sh
cd frontend
npm install
npm run dev        # http://localhost:5173
```

`npm run build` makes a production build in `dist/`.

## Data

- **`src/config.js`** — the one place that says where data comes from. `null` uses the bundled saved report; set
  it to the backend's `GET /api/report` when that's ready.
- **`src/data/capitol-hill-bakery-report.json`** — a copy of Ruth's example report (`scraping` branch), used for
  the demo.
- **`src/data/adapter.js`** — `toDashboard(raw)` turns the report into what the UI renders, with safe defaults for
  anything missing.
- **Load JSON** button, or drag a `.json` file anywhere on the page, to show the scraper's output live.

**[API.md](API.md)** documents the report format and what each field is used for.

## Map

- **Pins** come from `data/spots.geo.json`, made once with the free US Census geocoder so the demo never geocodes
  live. After a new report: `npm run geocode` (or `node scripts/geocode-spots.mjs <report.json>`). It logs any
  address that fails; those spots stay in the list without a pin. `lat`/`lng` in the report itself win.
- **License check** (`src/lib/verifyBusiness.ts`): queries Seattle's open license data
  (`cos-data.seattle.gov/resource/wnbq-64tb.json`, no key) by name, then matches on name + zip, or the exact street
  address when the zips disagree. Weak matches show **Unverified** with the reason; no record shows "Not found in
  Seattle license records". Sole proprietorships and single-member LLCs get a **Small business** tag. Results are
  cached in memory, and a failed lookup never breaks the card.
- Click a pin to highlight and scroll to its card; click a card to highlight its pin.

## Layout

- `src/App.jsx` — loading the data, file drop, top bar
- `src/components/` — header, "You vs nearby" cards, competitor table, complaint themes, suggestions,
  loading/empty/error states, `MapView` / `SpotMap` / `LicenseBadge`
- `src/lib/` — `verifyBusiness.ts` (license check), `spots.js` (adds saved coordinates)
- `scripts/geocode-spots.mjs` → `data/spots.geo.json`
- `src/styles.css` — design tokens (light + dark), glass cards, responsive layout
