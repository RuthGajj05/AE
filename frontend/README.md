# LocalEdge — frontend

Competitor insights for small food businesses in Seattle. One page reads a scraper report (Ruth's format) and shows
the market at a glance, who the nearby competitors are, what their customers complain about, what things cost, and
Claude's suggestions, with sources and caveats.

Vite + React + plain CSS. No login, no API keys.

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

## Layout

- `src/App.jsx` — loading the data, file drop, top bar
- `src/components/` — header, "You vs nearby" cards, competitor table, complaint themes, suggestions,
  loading/empty/error states
- `src/styles.css` — design tokens (light + dark), glass cards, responsive layout
