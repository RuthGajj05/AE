"""Make new alerts: Ruth's competitor monitor and the Square stock check, for one or every business.

    cd backend
    .venv/bin/python scripts/check_alerts.py --all               # every (non-demo) business
    .venv/bin/python scripts/check_alerts.py --business-id biz-…  # one business
    .venv/bin/python scripts/check_alerts.py --all --stock-only  # just Square counts (cheap; run hourly)

Run the monitor a few times a week (it re-researches competitors: Claude + Tavily) and the stock check hourly.
The first monitor run per business saves a baseline; later runs report changes. top_rated alerts need nothing
here: they come from re-scoring areas (scripts/prewarm.py --refresh).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import alerts  # noqa: E402
import config  # noqa: E402
import pipeline  # noqa: E402
import store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--all", action="store_true")
    target.add_argument("--business-id")
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--stock-only", action="store_true")
    which.add_argument("--monitor-only", action="store_true")
    args = parser.parse_args()

    store.init()
    businesses = store.list_businesses() if args.all else [b for b in [store.get_business(args.business_id)] if b]
    if not businesses:
        print("No businesses to check.")
        return 1
    do_monitor = not args.stock_only and all(config.has_key(k) for k in pipeline.LIVE_KEYS)
    do_stock = not args.monitor_only and config.has_key("SQUARE_ACCESS_TOKEN")
    if not do_monitor and not do_stock:
        print("Nothing to run: the monitor needs ANTHROPIC_API_KEY and TAVILY_API_KEY, the stock check SQUARE_ACCESS_TOKEN.")
        return 1

    failures = 0
    for b in businesses:
        if do_monitor:
            try:
                result = alerts.run_monitor(b["id"])
                print(f"{b['name']}: monitor {'baseline saved' if result['baseline'] else f'{result['changes']} change(s)'}")
            except Exception as e:
                failures += 1
                print(f"{b['name']}: monitor failed: {e}")
        if do_stock:
            try:
                result = alerts.check_stock(b["id"])
                print(f"{b['name']}: stock {result['items']} tracked item(s), {result['alertsAdded']} new alert(s)")
            except Exception as e:
                failures += 1
                print(f"{b['name']}: stock check failed: {e}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
