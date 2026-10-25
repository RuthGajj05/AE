# LocalEdge — frontend

Business-side dashboard for neighborhood food businesses in Seattle. An owner enters a few facts about their shop
(category, neighborhood, price of a benchmark item, typical wait, rating, review count) and sees:

- how their price, wait, rating and review count compare to nearby competitors
- ranked recommendations, each showing the numbers behind it
- what customers complain about at competing businesses, and how to use that
- market signals and a competitor table

No login. The profile is kept in the browser's localStorage.

## Backend

The scraping and Claude tips live on the backend. The frontend talks to it through two endpoints, documented in
**[API.md](API.md)** — that's the file to hand the backend team.

Until the backend is ready the app uses mock data (`src/api/mock.ts`, fictional businesses in
`src/data/sample.ts`) and labels it "Sample data". To switch to the real backend:

```sh
cp .env.example .env.local   # then set VITE_API_URL=http://localhost:8000 (no keys in this file)
npm run dev
```

Add `?mock` to the URL to force sample data (demo fallback), or `?demo` to skip the form with a demo bakery.

## Run it

```sh
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check and production build
```

## Layout

- `src/api/client.ts` — every backend call, plus cleanup of messy responses
- `src/api/mock.ts` — mock backend with the same response shapes
- `src/types.ts` — shared request/response types (mirrors API.md)
- `src/data/` — reference data (categories, neighborhoods, complaint themes) and sample competitors
- `src/lib/stats.ts` — medians and complaint totals for display
- `src/components/` — profile form, dashboard, charts, tables, loading and error states
