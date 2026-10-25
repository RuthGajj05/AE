"""Pre-score all five food types for Capitol Hill so the demo loads instantly (results are cached 24h).

    cd backend
    .venv/bin/python scripts/prewarm.py                 # all five, skip any still fresh in the cache
    .venv/bin/python scripts/prewarm.py --refresh       # re-score even if cached
    .venv/bin/python scripts/prewarm.py --cuisine sushi --depth deep

Needs ANTHROPIC_API_KEY and TAVILY_API_KEY in backend/.env. Each food type takes a minute or two live.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402  (loads backend/.env)
import cuisines  # noqa: E402
import pipeline  # noqa: E402
import store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cuisine", choices=[c["id"] for c in cuisines.CUISINES], action="append",
                        help="only this food type (repeatable); default: all five")
    parser.add_argument("--depth", choices=["fast", "deep"], default="fast")
    parser.add_argument("--refresh", action="store_true", help="re-score even if a fresh result is cached")
    args = parser.parse_args()

    store.init()
    try:
        pipeline.require_live_keys()
    except pipeline.NotConfigured as e:
        print(e)
        return 1

    hill = config.CAPITOL_HILL
    failures = 0
    for cuisine in args.cuisine or [c["id"] for c in cuisines.CUISINES]:
        start = time.monotonic()
        try:
            payload = pipeline.get_spots(cuisine, hill["lat"], hill["lng"], hill["radiusMi"], depth=args.depth, refresh=args.refresh)
        except Exception as e:
            failures += 1
            print(f"{cuisine:6} failed: {e}")
            continue
        pick = next((s["name"] for s in payload["spots"] if s["id"] == payload["pickId"]), "none")
        print(f"{cuisine:6} {len(payload['spots'])} spots, {payload['reviewsRead']} reviews read, pick: {pick} "
              f"[{payload['source']}, {payload['collectionStatus']}] in {time.monotonic() - start:.0f}s")
        for caveat in payload.get("caveats", []):
            print(f"       note: {caveat}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
