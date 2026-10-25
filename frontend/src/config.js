// Where the dashboard gets its data. This is the only place to change it.
//
//   null                                → the saved report bundled with the app (demo default)
//   '/scraper-output.json'              → a report file dropped into frontend/public/
//   'http://localhost:8000/api/report'  → Neha's backend: latest saved report (must allow CORS)
//
// You can also drag a JSON file onto the page at any time; that overrides this until reload.
// No API keys here: everything in the frontend is visible to anyone who opens the page.
export const DATA_URL = null
