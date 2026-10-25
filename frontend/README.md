# LocalEdge — frontend

Competitor insights for small food businesses in Seattle. One page shows how a business compares with nearby
competitors on price, wait time and rating, who those competitors are, what their customers complain about, and
Claude's suggestions for what to do next.

Vite + React + plain CSS. No login, no API keys.

## Run it

```sh
cd frontend
npm install
npm run dev        # http://localhost:5173
```

`npm run build` makes a production build in `dist/`.

## Data

- **`src/config.js`** — the one place that says where data comes from. `null` uses the bundled sample; set it to a
  file in `public/` or the backend's URL when the scraper is ready.
- **`src/data/sample.json`** — sample data (fictional businesses): 1 business, 5 competitors, 6 review themes,
  4 suggestions.
- **`src/data/adapter.js`** — `toDashboard(raw)` turns whatever JSON the scraper sends into what the UI renders,
  with safe defaults for anything missing.
- **Load JSON** button, or drag a `.json` file anywhere on the page, to show the scraper's output live.

**[API.md](API.md)** is the data format to hand to the backend team.

## Layout

- `src/App.jsx` — loading the data, file drop, top bar
- `src/components/` — header, "You vs nearby" cards, competitor table, complaint themes, suggestions,
  loading/empty/error states
- `src/styles.css` — design tokens (light + dark), glass cards, responsive layout
