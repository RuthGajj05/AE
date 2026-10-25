# AE

Tailored advice for small, brick-and-mortar businesses. Given a business, its location and its sales data, it researches nearby competitors and the business's own online presence in parallel, then writes recommendations specific to what that business lacks or could change, with estimated dollar impact.

```
              ┌─ competitor research (agent)            ─┐
in parallel ──┼─ your online presence (agent)           ─┼─→ advisor → tailored recommendations
              └─ your sales data (plain Python analysis) ─┘
```

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

Full pipeline (about 2.5 minutes):

```sh
.venv/bin/python agent/advisor.py "Test Bakery" bakery "Capitol Hill, Seattle" --sales data/sample_sales.csv
```

`--sales` takes a Square "Items" sales export (CSV with Date, Time, Category, Item, Qty, Gross Sales). `data/sample_sales.csv` is **fake** data for a fictional bakery, made by `scripts/make_sample_sales.py`.

The report is saved to `reports/<business>-<date>-advisor.json`. Progress and timings print as it runs.

Competitor research only:

```sh
.venv/bin/python agent/competitor_agent.py "Test Bakery" bakery "Capitol Hill, Seattle"
```

## Examples

- [`examples/capitol-hill-bakery-advisor.json`](examples/capitol-hill-bakery-advisor.json): full advisor report for the fictional "Test Bakery" on Capitol Hill, using the fake sample sales.
- [`examples/capitol-hill-bakery-report.json`](examples/capitol-hill-bakery-report.json): an earlier competitor-only report (older format, which also included recommendations).

## Files

- `agent/advisor.py`: runs the three parts in parallel and writes the tailored recommendations
- `agent/competitor_agent.py`: competitor research agent and its tools (OpenStreetMap, Tavily, optional Google Places)
- `agent/business_agent.py`: sales-data analysis and the agent that researches the business's own online presence
- `agent/agent_loop.py`: shared agent loop that runs each turn's tool calls in parallel
- `agent/sources.py`: which sites web search uses for listings and reviews
- `scripts/make_sample_sales.py`: generates the fake sample sales data
