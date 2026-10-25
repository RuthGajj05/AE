# AE

Competitor research agent for small, brick-and-mortar businesses. Given a business and its location, it finds nearby competitors, reads their reviews and prices, and writes a structured report with evidence-backed recommendations.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Put your keys in a `.env` file at the repo root (it's gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
GOOGLE_PLACES_API_KEY=...
```

`GOOGLE_PLACES_API_KEY` is optional and paid. Without it, the agent finds competitors with OpenStreetMap (free, no key) and gets ratings and reviews from web search. To get a Google key: in the [Google Cloud console](https://console.cloud.google.com/), create a project, enable billing and **Places API (New)**, then create an API key under APIs & Services → Credentials. Restrict the key to Places API (New).

## Run

```sh
.venv/bin/python agent/competitor_agent.py "Sweet Crumb Bakery" bakery "Capitol Hill, Seattle"
```

Progress prints as the agent searches. The report is saved to `reports/<business>-<date>.json`.

See [`examples/capitol-hill-bakery-report.json`](examples/capitol-hill-bakery-report.json) for a sample report: a test run for a hypothetical bakery on Capitol Hill, Seattle.

## Files

- `agent/competitor_agent.py`: the agent (Claude + Tavily tools + report schema)
- `agent/sources.py`: which sites to search for listings and reviews; edit this to change sources
