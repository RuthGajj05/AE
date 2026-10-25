"""Rebuild backend/demo/ from the frontend's mock JSON (frontend/src/crumbs/data/), in the API's shapes.

    python scripts/build_demo_fixtures.py path/to/frontend/src/crumbs/data

The frontend mock uses made-up spot names so no real business gets fake scores; the fixtures keep that.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import cuisines  # noqa: E402
import geo  # noqa: E402
import scoring  # noqa: E402

SCRAPED_AT = "2026-10-25T17:00:00+00:00"
NOTE = "Sample data: made-up spot names and scores, for the stage demo. Not real businesses."


def spots_fixture(c: dict) -> dict:
    hill = config.CAPITOL_HILL
    spots = []
    for s in c["spots"]:
        spots.append({
            "id": s["id"], "name": s["name"], "lat": s["lat"], "lng": s["lng"],
            "address": f"{s['street']}, Seattle, WA", "street": s["street"], "price": s["price"],
            "distanceMi": round(geo.miles_between(hill["lat"], hill["lng"], s["lat"], s["lng"]), 2),
            "scores": s["scores"], "waitMinutes": s["waitMinutes"], "ambiancePct": s["ambiancePct"],
            "ambianceMentionRate": s["ambianceMentionRate"], "bestAt": s["bestAt"], "reason": s["reason"],
            "reviewCount": s["reviewCount"], "sourceKinds": ["demo"], "collectionStatus": "complete",
            "rating": None, "platformReviewCount": None, "pick": s["pick"],
            "openUntil": s.get("openUntil"), "phone": s.get("phone"),
        })
    top = next(s for s in spots if s["pick"])
    return {
        "cuisine": c["id"], "spots": spots, "pickId": top["id"], "pickReason": top["reason"],
        "areaAverages": scoring.area_averages(spots, cuisines.compare_attributes(c["id"])),
        "reviewsRead": sum(s["reviewCount"] for s in spots), "scrapedAt": SCRAPED_AT, "source": "demo", "demo": True,
        "collectionStatus": "complete", "caveats": [NOTE],
    }


def main(data_dir: Path) -> None:
    out = Path(__file__).resolve().parent.parent / "demo"
    out.mkdir(exist_ok=True)
    for c in json.loads((data_dir / "cuisines.json").read_text())["cuisines"]:
        (out / f"spots-{c['id']}.json").write_text(json.dumps(spots_fixture(c), indent=2) + "\n")
    business = json.loads((data_dir / "business.json").read_text())
    (out / "business.json").write_text(json.dumps({
        "note": NOTE, "id": "biz-tamago", "name": business["you"]["name"], "cuisine": business["you"]["cuisine"],
        "area": business["area"], "goals": ["Shorter waits", "Rice"],
        "you": {**business["you"], "id": "biz-tamago", "reviewCount": 180},
        # 30 seeded picks: 9 won, 21 lost (frontend sample proportions, scaled up).
        "seedPicks": {"won": 9, "lostTo": {"sushi-hikari": 11, "sushi-umi": 5, "sushi-pike-roll": 3, "sushi-nori-house": 2}},
    }, indent=2) + "\n")
    places = json.loads((data_dir / "mock-places.json").read_text())["places"]
    (out / "places.json").write_text(json.dumps({"note": NOTE, "results": [
        {"placeId": f"demo:{p['id']}", "name": p["name"], "address": p["address"], "lat": p["lat"], "lng": p["lng"], "source": "demo"}
        for p in places]}, indent=2) + "\n")
    print(f"Wrote fixtures to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
