# crumbs + LocalEdge — frontend

Two apps in one Vite project:

- **crumbs** (`/`, the main app): a phone-style app for Capitol Hill food spots, one nav for every account:
  **Home** (business dashboard), **Alerts**, **Map** (center), **Saved**, **You**. Code in `src/crumbs/`.
- **LocalEdge** (`/localedge.html`): the competitor dashboard below. Code in `src/App.jsx` and `src/components/`.

## crumbs: Google Maps key

```sh
cp .env.example .env.local   # then paste your key after VITE_GOOGLE_MAPS_API_KEY=
```

- `.env.local` is git-ignored. Never commit the key.
- Enable **Maps JavaScript API** and **Places API (New)** for the key, and restrict it to your site's URLs
  (HTTP referrers) in Google Cloud. A Maps browser key is visible to anyone who opens the page; the restriction is
  what protects it.
- **No key?** The app still runs: it shows 10 sample spots (`src/crumbs/data/mock-places.json`) on a free Stadia Maps
  base map (no key on localhost; for a deployed URL, add the domain to a free Stadia account) and says "Sample places" at the top. If the key works but Places fails, it shows the same sample spots on the
  Google map (the reason is logged in the console).
- `src/crumbs/places.js` is the one data file: Places search, sample places, and the review-score stub.
- Freshness / Value / Service chips show "—" until the backend's review analysis exists (contract in API.md).
- Food chips open a draggable compare sheet (peek / half / full) with a crumbs pick, a score chart and a sortable
  list. Data: `src/crumbs/data/cuisines.json` (sample), loaded through `getCuisine(id)`. Wait is minutes, Ambiance is
  % positive.
- Tapping a spot opens **Go here**: dotted walk on the map, stats, and a Google Maps link that saves an anonymous
  pick (localStorage for now).
- **Accounts** (demo, localStorage): Member or Business. Switch in **You → Switch account type**, or tap
  **I run a spot** on Home to run the short business onboarding. Businesses land on Home, Members on the Map.
- **Home** is the business side: ring-style **Insights** (Reputation, Momentum, Edge, breakdown vs the area, Biggest
  drag, The gap) and **Rivals** (picks lost and why), from the backend or `src/crumbs/data/business.json` plus this
  browser's picks. Members see it locked.
- **Alerts**: nearby changes (fresh stock, top rated, price, new spots) plus owner alerts for businesses, from
  `GET /api/alerts` (backend demo set when it has none yet, `src/crumbs/data/alerts.json` when it's down). Tap opens
  the spot's Go here sheet. Unread count on the tab.
- **Saved**: spots saved from Go here (localStorage). **You**: profile, favorite foods, alert settings.
- **Sharing the dev server** (tunnel link or local network): pages load for anyone, but `/api` only answers on this
  laptop, so shared viewers see sample data and can't spend the backend's API credits. To let them reach the backend
  on purpose, start the dev server with `SHARE_API=1 npm run dev`.

## LocalEdge

Competitor insights for small food businesses in Seattle. One page reads a scraper report (Ruth's format) and shows
the market at a glance, who the nearby competitors are, what their customers complain about, what things cost, and
Claude's suggestions, with sources and caveats.

Two views from the same report: **Dashboard** and **Map** (`#/map`), an Airbnb-style list of spot cards beside a
Leaflet map with price pins. Each card checks the shop against Seattle's business license records.

Vite + React + plain CSS + Leaflet (free OpenStreetMap tiles). No login, no API keys.

(crumbs uses a Google Maps browser key from `.env.local`; see above.)

## Run it

```sh
cd frontend
npm install
npm run dev        # crumbs: http://localhost:5173  ·  LocalEdge: http://localhost:5173/localedge.html
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
