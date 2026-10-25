"""crumbs endpoints (contract: backend/API.md). Errors are {"error": "plain-English message"}; main.py
turns HTTPException into that shape."""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

import config
import cuisines
import demo
import geo
import pipeline
import store

router = APIRouter(prefix="/api")

CUISINE_IDS = ", ".join(c["id"] for c in cuisines.CUISINES)


def _demo(flag: bool) -> bool:
    return flag or config.demo_mode()


def _cuisine(cuisine_id: str) -> str:
    if not cuisines.get(cuisine_id):
        raise HTTPException(400, f"Unknown food type “{cuisine_id}”. Try one of: {CUISINE_IDS}.")
    return cuisine_id


# ---------- consumer ----------

@router.get("/cuisines")
def list_cuisines():
    return [cuisines.public(c) for c in cuisines.CUISINES]


@router.get("/spots")
def list_spots(
    cuisine: str,
    lat: float = Query(config.CAPITOL_HILL["lat"], ge=-90, le=90),
    lng: float = Query(config.CAPITOL_HILL["lng"], ge=-180, le=180),
    radiusMi: float = Query(1.0, ge=0.1, le=5),
    depth: Literal["fast", "deep"] = "fast",
    refresh: bool = False,
    demo_flag: bool = Query(False, alias="demo"),
):
    cuisine = _cuisine(cuisine)
    if _demo(demo_flag):
        return demo.spots(cuisine)
    try:
        return pipeline.get_spots(cuisine, lat, lng, radiusMi, depth=depth, refresh=refresh)
    except pipeline.NotConfigured as e:
        raise HTTPException(503, str(e))
    except pipeline.CollectionFailed as e:
        raise HTTPException(502, str(e))


@router.get("/spots/{spot_id}")
def get_spot(spot_id: str, cuisine: str | None = None, demo_flag: bool = Query(False, alias="demo")):
    detail = demo.spot_detail(spot_id) if _demo(demo_flag) else pipeline.spot_detail(spot_id, cuisine)
    if detail is None and not _demo(demo_flag):
        detail = demo.spot_detail(spot_id)  # demo spot ids still resolve when demo mode is off
    if detail is None:
        raise HTTPException(404, "We couldn't find that spot. It may not have been scored yet.")
    return detail


class PickIn(BaseModel):
    # Only these three fields are read; anything else a client sends is ignored, never stored.
    model_config = ConfigDict(extra="ignore")
    cuisine: str
    chosenSpotId: str = Field(min_length=1, max_length=120)
    comparedSpotIds: list[str] = Field(default_factory=list, max_length=12)


@router.post("/picks")
def record_pick(pick: PickIn):
    cuisine = _cuisine(pick.cuisine)
    compared = list(dict.fromkeys([*(s[:120] for s in pick.comparedSpotIds if s), pick.chosenSpotId]))
    store.add_pick(cuisine, pick.chosenSpotId, compared)  # anonymous: no user id, IP or device data
    return {"ok": True}


# ---------- business ----------

@router.get("/places/search")
def places_search(q: str = Query(min_length=2, max_length=120), demo_flag: bool = Query(False, alias="demo")):
    if _demo(demo_flag):
        return {"results": demo.places(q), "source": "demo"}
    try:
        results = geo.search_places(q)
    except Exception:
        raise HTTPException(502, "Place search isn't responding right now. Try again, or type the name and address.")
    return {"results": results, "source": "google" if config.has_key("GOOGLE_PLACES_API_KEY") else "osm"}


class Questionnaire(BaseModel):
    """Manny's business profile fields (main: lib/business-profile.ts). All optional."""
    model_config = ConfigDict(extra="ignore")
    businessType: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=160)
    offerings: str | None = Field(None, max_length=600)
    customers: str | None = Field(None, max_length=400)
    currentApproach: str | None = Field(None, max_length=600)
    constraints: str | None = Field(None, max_length=600)


class OnboardIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    placeId: str | None = Field(None, max_length=300)
    name: str | None = Field(None, max_length=160)
    address: str | None = Field(None, max_length=300)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    cuisine: str
    goals: list[str] = Field(default_factory=list, max_length=10)
    questionnaire: Questionnaire = Field(default_factory=Questionnaire)
    deepResearch: bool = False


@router.post("/business/onboard")
def onboard(body: OnboardIn, background: BackgroundTasks, demo_flag: bool = Query(False, alias="demo")):
    cuisine = _cuisine(body.cuisine)
    if _demo(demo_flag):
        return {"businessId": demo.BUSINESS_ID, "status": "complete", "demo": True}
    if not body.placeId and not body.name:
        raise HTTPException(400, "Tell us the business name, or pick it from search.")
    try:
        business_id = pipeline.onboard(
            cuisine=cuisine, name=body.name, address=body.address, place_id=body.placeId, lat=body.lat, lng=body.lng,
            goals=[g.strip()[:80] for g in body.goals if g.strip()],
            questionnaire={k: v.strip() for k, v in body.questionnaire.model_dump().items() if v and v.strip()},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    background.add_task(pipeline.score_business, business_id, body.deepResearch)
    return {"businessId": business_id, "status": "queued"}


@router.get("/business/{business_id}/insights")
def business_insights(business_id: str, demo_flag: bool = Query(False, alias="demo")):
    result = pipeline.insights(demo.BUSINESS_ID if _demo(demo_flag) else business_id)
    if result is None:
        raise HTTPException(404, "We couldn't find that business. Try onboarding it again.")
    return result


@router.get("/business/{business_id}/rivals")
def business_rivals(business_id: str, days: int = Query(7, ge=1, le=90), demo_flag: bool = Query(False, alias="demo")):
    result = pipeline.rivals(demo.BUSINESS_ID if _demo(demo_flag) else business_id, days)
    if result is None:
        raise HTTPException(404, "We couldn't find that business. Try onboarding it again.")
    return result
