# Backend integration contract

The application team can call these Python functions from its own worker or invoke the CLI and read its JSON output. No HTTP routes, frontend components, or automatic schedule are supplied here. Live calls need the configured service credentials; offline analysis does not.

## Collect and analyze

From the repository root, or with the repository on your Python import path:

```python
from agent.competitor_agent import research

report = research(
    "Example Bakery",
    "bakery",
    "Exact branch address, city",
    owner_menu={
        "products": ["Butter croissant", "Coffee"],
        "confirmed_complete": False,
        "confirmed_at": None,
    },
    reports_dir="reports",
    window_days=30,
    min_reviews=10,
    use_history=True,
    max_workers=4,
    save=True,
)
```

`research(...)` returns a JSON-ready dictionary after collection, history merging, and product analysis. It is synchronous; the calling application should run it in its own worker. `save=True` also writes a report but does not add a filesystem path to the returned contract. `save=False` skips writing; use `use_history=False` as well for an isolated run.

The original `run(business, business_type, location, owner_menu=None, *, max_workers=4)` remains the facts collector. It returns competitor research and current observations without product analysis or persistence. Use `research(...)` for the combined contract, or `analyze_report(...)` when coordinating the existing advisor pipeline.

`analyze_report(report, owner_menu, *, reports_dir=REPORTS_DIR, as_of=None, window_days=30, min_reviews=10, use_history=True)` takes the collector's dictionary and a validated `OwnerMenu`. It enriches and returns that dictionary without collecting more pages. `as_of` is a Python `date` when supplied.

## Keep the existing advisor pipeline

```python
from pathlib import Path
from agent.advisor import run as advise

report = advise(
    "Example Bakery", "bakery", "Exact branch address, city",
    sales_csv="/path/to/sales.csv",
    website="https://example.com",
    owner_menu={"products": ["Butter croissant"],
                "confirmed_complete": False, "confirmed_at": None},
    max_workers=4,
    reports_dir=Path("reports"),
    use_history=True,
    synthetic_sales=False,
)
```

The advisor retains its parallel competitor, online-presence, and sales stages. It runs deterministic product analysis after those inputs arrive and before Claude writes advice. With no explicit owner menu, positively sold items become known products with `confirmed_complete=False` and no confirmation date. A separate competitor snapshot supplies incremental history.

The returned advisor dictionary retains `advice`, `your_sales`, `your_online_presence`, and `competitors`. `competitors` contains the enriched competitor report described below; the advisor also exposes `market_intelligence`, `owner_menu`, `evidence_bundle`, and `source_coverage`. Its top-level `mode` is `advisor`, or `demo` for recognized/declared synthetic sales. Use the nested `competitors` report for the complete portable analysis bundle and its collection-mode metadata.

`advice` contains `snapshot`, `strengths`, `gaps_vs_competitors`, `recommendations`, and `caveats`. Each recommendation retains its title, category, action, business/market evidence, confidence, `est_monthly_impact_usd`, and `impact_math`. A null impact is unavailable, not zero; any numeric impact is an assumption-based scenario. `competitor_snapshot` is a local saved-file path for the backend, not a customer-facing source URL.

`your_sales` carries `is_synthetic`, `data_origin`, and caveats. The repository's exact `data/sample_sales.csv` is recognized automatically; callers must mark other fake inputs with `synthetic_sales=True`. Preserve this distinction in the application's display and exports.

## Inputs

Owner menu:

```json
{
  "products": ["Butter croissant", "Coffee"],
  "confirmed_complete": false,
  "confirmed_at": null
}
```

A confirmation date uses `YYYY-MM-DD`. An unconfirmed menu can identify known products but cannot prove that another product is absent. A sales export likewise establishes what sold during that period, not the complete current menu. Menu confirmation must come from the owner, not from an inferred list.

An evidence bundle has two arrays:

| Array | Required fields | Optional fields |
|---|---|---|
| `menu_observations` | `business_name`, `address`, `product`, `source_url`, `observed_at` | `price` |
| `review_observations` | `business_name`, `address`, `source_url`, `text` | `published_at`, `source_kind`, `mentions`, `review_id`, `observed_at` |

Use explicit `source_kind` values: `review_text`, `search_snippet`, `editorial`, or `google_places_sample`. The default is conservatively `search_snippet`. Each `mentions` entry contains a product name and sentiment: `positive`, `negative`, `neutral`, or `request`. Dates use `YYYY-MM-DD`; unknown publication dates are `null`. Source URLs must be absolute HTTP(S) URLs. See [the synthetic fixture](../examples/product-opportunity-demo.json) for a complete example.

Supply all collected review texts, including reviews with no product mentions, so the denominator is meaningful. Do not relabel snippets as full reviews, invent dates, or infer publication dates from retrieval time. Imported classification is supplied by the caller; offline analysis does not independently fetch or verify sources. Invalid structured inputs raise validation errors.

## Analyzed report fields

| Field | Meaning |
|---|---|
| `business`, `type`, `location`, `date` | Target identity and report metadata. Use the exact branch consistently. |
| `mode` | `live_research` or `imported_evidence`; history is isolated by mode. |
| `competitors`, `gaps_and_caveats` | Collector's factual output. There is no collector summary, advice, or price-benchmark field. |
| `source_coverage` | Available for live collection: retrieval kinds and failed extractions, not a collected-review total. |
| `schema_version`, `captured_at`, `history_reports_used` | Current schema version (`2`), capture timestamp, and number of contributing history reports. |
| `owner_menu` | Owner-supplied products and confirmation state. |
| `analysis_date` | Date used for the comparison windows. |
| `evidence_bundle` | Observations from this run/input only; used for incremental history. |
| `analysis_evidence_bundle` | Complete merged evidence used for this analysis; portable replay input. |
| `market_intelligence` | Deterministic product gaps, review trends, evidence counts, and limitations. |

`market_intelligence.product_gaps` includes the product, owner-menu status (`confirmed_absent` or `needs_confirmation`), competitor names/addresses/count, positive/request/negative review counts, source URLs, confidence, limitations, and a measurable experiment. Counts can overlap across sentiments. Confidence is descriptive, not a statistical confidence interval or forecast.

`market_intelligence.product_trends` includes the product and status (`rising`, `falling`, `stable`, or `insufficient_evidence`); previous/current date ranges, denominators, positive-or-request counts, raw and standardized shares; change in percentage points; matching business/source groups; sources; and limitations. Shares are fractions from 0 to 1. A value of `0.25` displays as 25%. A null share/change is unavailable, not zero.

A useful application view shows the status, counts and periods beside every claim, with links to supporting sources. An `insufficient_evidence` result is a valid output. Do not turn it into a growth claim or equate review interest with units sold.

## Replay an exported report

Prefer `analysis_evidence_bundle` when present, because it contains the historical observations used in the original calculation. Fall back to `evidence_bundle` only when the preferred field is absent. If the preferred field exists but is malformed, reject it rather than silently changing the evidence. Do not trust a caller-provided `market_intelligence` result; recalculate it.

```python
import json
from datetime import date
from agent.market_intelligence import EvidenceBundle, OwnerMenu, analyze_market

with open("exported-report.json") as stream:
    exported = json.load(stream)

raw = (exported["analysis_evidence_bundle"]
       if "analysis_evidence_bundle" in exported
       else exported["evidence_bundle"])
evidence = EvidenceBundle.model_validate(raw)
owner = OwnerMenu.model_validate(exported["owner_menu"])
settings = exported.get("market_intelligence", {})
result = analyze_market(
    exported["business"],
    exported["location"],
    owner_menu=owner,
    evidence=evidence,
    as_of=date.fromisoformat(exported["analysis_date"]),
    window_days=int(settings.get("window_days", 30)),
    min_reviews_per_period=int(settings.get("min_reviews_per_period", 10)),
    min_product_mentions_per_period=int(settings.get("min_product_mentions_per_period", 3)),
    menu_max_age_days=int(settings.get("menu_max_age_days", 90)),
)
print(result.model_dump_json(indent=2))
```

Validate and bound any caller-selected analysis settings in the host application. Retain an explicit synthetic-data label when transporting demo fixtures. Replaying source observations does not make synthetic data real.

Saved history reads only each prior report's `evidence_bundle`, not its already-merged `analysis_evidence_bundle`, avoiding recursive growth. Name, location, mode, and analysis date determine which saved records can contribute. No histories from other locations or later analysis dates should be combined implicitly.
