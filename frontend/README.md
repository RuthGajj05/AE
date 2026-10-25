# LocalEdge — frontend

Business-side dashboard for neighborhood food businesses in Seattle. An owner enters a few facts about their shop
(category, neighborhood, price of a benchmark item, typical wait, rating, review count) and sees:

- how their price, wait, rating and review count compare to nearby competitors
- ranked recommendations, each showing the numbers behind it
- what customers complain about at competing businesses, and how to use that
- market signals and a competitor table

No login. The profile is kept in the browser's localStorage.

All competitor and trend data is **sample data** (fictional businesses) in `src/data/sample.ts`. It stands in for the
web research step until that is built.

## Run it

```sh
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check and production build
```

## Layout

- `src/data/` — reference data (categories, neighborhoods, complaint themes) and sample competitors
- `src/lib/insights.ts` — comparisons and recommendation rules
- `src/components/` — profile form, dashboard, charts and tables
