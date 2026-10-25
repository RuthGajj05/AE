// Where the dashboard gets its data. This is the only place to change it.
//
//   null                                  → bundled sample data (src/data/sample.json)
//   '/scraper-output.json'                → a JSON file dropped into frontend/public/
//   'http://localhost:8000/api/dashboard' → the backend (it must allow CORS from this page)
//
// You can also drag a JSON file onto the page at any time; that overrides this until reload.
// No API keys here: everything in the frontend is visible to anyone who opens the page.
export const DATA_URL = null
