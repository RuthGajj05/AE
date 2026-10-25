"""crumbs endpoints (contract: backend/API.md). Errors are {"error": "plain-English message"}; main.py
turns HTTPException into that shape."""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

import alerts
import auth
import config
import cuisines
import demo
import geo
import pipeline
import reports
import sales
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
    # One of crumbs' food types (sushi, ramen, …) and/or the owner's own words ("bakery", "cafe"). Any business can
    # onboard; crumbs' review scoring (Insights, Rivals) runs only for its food types.
    cuisine: str | None = None
    businessType: str | None = Field(None, max_length=60)
    goals: list[str] = Field(default_factory=list, max_length=10)
    questionnaire: Questionnaire = Field(default_factory=Questionnaire)
    deepResearch: bool = False
    # Ruth's advisor: tailored recommendations from competitor research (about a minute, in the background)
    advisorReport: bool = True
    # Public "fresh shipment" alerts from Square restocks; off unless the owner opts in. Counts are never public.
    shareStockAlerts: bool = False
    lowStockThreshold: float | None = Field(None, ge=0, le=100000)


@router.post("/business/onboard")
def onboard(body: OnboardIn, background: BackgroundTasks, demo_flag: bool = Query(False, alias="demo"),
            user: dict | None = Depends(auth.current_user)):
    kind = " ".join((body.businessType or "").split())
    cuisine = _cuisine(body.cuisine) if body.cuisine else cuisines.match(kind)
    if not cuisine and not kind:
        raise HTTPException(400, "Tell us what kind of business it is, like bakery, cafe or sushi.")
    if _demo(demo_flag):
        return {"businessId": demo.BUSINESS_ID, "status": "complete", "demo": True}
    auth.require_user(user)
    if not body.placeId and not body.name:
        raise HTTPException(400, "Tell us the business name, or pick it from search.")
    try:
        business_id = pipeline.onboard(
            cuisine=cuisine or kind.lower(), name=body.name, address=body.address, place_id=body.placeId, lat=body.lat, lng=body.lng,
            goals=[g.strip()[:80] for g in body.goals if g.strip()],
            questionnaire={k: v.strip() for k, v in body.questionnaire.model_dump().items() if v and v.strip()},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    settings = {"share_stock_alerts": int(body.shareStockAlerts), "owner_user_id": user["id"] if user else None,
                "owner_email": (user or {}).get("email"), "kind": kind or None}
    if body.lowStockThreshold is not None:
        settings["low_stock_threshold"] = body.lowStockThreshold
    if not cuisine:
        settings["scoring_status"] = "unsupported"
    store.update_business(business_id, **settings)
    if cuisine:
        background.add_task(pipeline.score_business, business_id, body.deepResearch)
    report_queued = body.advisorReport and all(config.has_key(k) for k in pipeline.LIVE_KEYS)
    if report_queued:
        report_id, _ = reports.start(business_id)
        background.add_task(reports.run, business_id, report_id)
    return {"businessId": business_id, "status": "queued", "reportQueued": report_queued, "cuisine": cuisine}


@router.get("/business/{business_id}/insights")
def business_insights(business_id: str, demo_flag: bool = Query(False, alias="demo"),
                      user: dict | None = Depends(auth.current_user)):
    if not _demo(demo_flag) and store.get_business(business_id) is not None:
        auth.check_owner(store.get_business(business_id), user)
    result = pipeline.insights(demo.BUSINESS_ID if _demo(demo_flag) else business_id)
    if result is None:
        raise HTTPException(404, "We couldn't find that business. Try onboarding it again.")
    return result


@router.get("/business/{business_id}/rivals")
def business_rivals(business_id: str, days: int = Query(7, ge=1, le=90), demo_flag: bool = Query(False, alias="demo"),
                    user: dict | None = Depends(auth.current_user)):
    if not _demo(demo_flag) and store.get_business(business_id) is not None:
        auth.check_owner(store.get_business(business_id), user)
    result = pipeline.rivals(demo.BUSINESS_ID if _demo(demo_flag) else business_id, days)
    if result is None:
        raise HTTPException(404, "We couldn't find that business. Try onboarding it again.")
    return result


# ---------- signed-in owner ----------

@router.get("/me")
def me(user: dict | None = Depends(auth.current_user)):
    """The signed-in owner and their spot, so a new device can restore the business account."""
    auth.require_user(user)
    b = store.business_for_owner(user["id"]) if user else None
    business = {"id": b["id"], "name": b["name"], "address": b["address"],
                "cuisine": b["business_type"] if cuisines.get(b["business_type"]) else None,
                "type": b.get("kind") or b["business_type"]} if b else None
    return {"user": user, "authEnabled": auth.enabled(), "business": business}


# ---------- sales data (optional: CSV, Square or Toast) ----------

class CsvIn(BaseModel):
    filename: str = Field("sales.csv", max_length=200)
    content: str = Field(min_length=1, max_length=sales.MAX_CSV_BYTES)


class SquareIn(BaseModel):
    accessToken: str = Field(min_length=10, max_length=500)
    environment: Literal["production", "sandbox"] = "production"


class ToastIn(BaseModel):
    clientId: str = Field(min_length=3, max_length=200)
    clientSecret: str = Field(min_length=3, max_length=500)
    restaurantGuid: str = Field(min_length=3, max_length=100)


def _owned(business_id: str, user: dict | None) -> dict:
    b = auth.check_owner(store.get_business(business_id), user)
    if b["demo"]:
        raise HTTPException(400, "The sample business can't connect sales. Set up your own spot first.")
    return b


def _connected(business_id: str, background: BackgroundTasks, refresh_report: bool, connect) -> dict:
    """Run a connection check, then (by default) start a fresh report that uses the new sales."""
    try:
        connect()
    except ValueError as e:
        raise HTTPException(400, str(e))
    report_started = refresh_report and all(config.has_key(k) for k in pipeline.LIVE_KEYS)
    if report_started:
        report_id, already = reports.start(business_id)
        if not already:
            background.add_task(reports.run, business_id, report_id)
    return {**sales.status(store.get_business(business_id)), "reportStarted": report_started}


@router.get("/business/{business_id}/sales")
def sales_status(business_id: str, user: dict | None = Depends(auth.current_user)):
    return sales.status(auth.check_owner(store.get_business(business_id), user))


@router.post("/business/{business_id}/sales/csv")
def connect_csv(business_id: str, body: CsvIn, background: BackgroundTasks, refreshReport: bool = True,
                user: dict | None = Depends(auth.current_user)):
    _owned(business_id, user)
    return _connected(business_id, background, refreshReport,
                      lambda: sales.connect_csv(business_id, body.filename, body.content))


@router.post("/business/{business_id}/sales/square")
def connect_square(business_id: str, body: SquareIn, background: BackgroundTasks, refreshReport: bool = True,
                   user: dict | None = Depends(auth.current_user)):
    _owned(business_id, user)
    return _connected(business_id, background, refreshReport,
                      lambda: sales.connect_square(business_id, body.accessToken, body.environment))


@router.post("/business/{business_id}/sales/toast")
def connect_toast(business_id: str, body: ToastIn, background: BackgroundTasks, refreshReport: bool = True,
                  user: dict | None = Depends(auth.current_user)):
    _owned(business_id, user)
    return _connected(business_id, background, refreshReport,
                      lambda: sales.connect_toast(business_id, body.clientId, body.clientSecret, body.restaurantGuid))


@router.delete("/business/{business_id}/sales")
def disconnect_sales(business_id: str, user: dict | None = Depends(auth.current_user)):
    _owned(business_id, user)
    sales.disconnect(business_id)
    return sales.status(store.get_business(business_id))


# ---------- owner settings: alert emails ----------

class SettingsIn(BaseModel):
    emailAlerts: bool


def _settings(b: dict) -> dict:
    log = store.email_log(b["id"], limit=5)
    return {"emailAlerts": bool(b.get("email_alerts", 1)), "ownerEmail": b.get("owner_email"),
            "recentEmails": [{"subject": e["subject"], "status": e["status"], "detail": e["detail"],
                              "createdAt": e["created_at"]} for e in log]}


@router.get("/business/{business_id}/settings")
def business_settings(business_id: str, user: dict | None = Depends(auth.current_user)):
    return _settings(auth.check_owner(store.get_business(business_id), user))


@router.post("/business/{business_id}/settings")
def update_settings(business_id: str, body: SettingsIn, user: dict | None = Depends(auth.current_user)):
    _owned(business_id, user)
    store.update_business(business_id, email_alerts=int(body.emailAlerts))
    return _settings(store.get_business(business_id))


# ---------- advisor reports (Ruth's advisor) ----------

@router.get("/business/{business_id}/report")
def business_report(business_id: str, demo_flag: bool = Query(False, alias="demo"),
                    user: dict | None = Depends(auth.current_user)):
    b = None if _demo(demo_flag) else auth.check_owner(store.get_business(business_id), user)
    return reports.view(business_id, demo=_demo(demo_flag) or bool(b and b["demo"]))


@router.post("/business/{business_id}/report", status_code=202)
def refresh_business_report(business_id: str, background: BackgroundTasks, user: dict | None = Depends(auth.current_user)):
    b = auth.check_owner(store.get_business(business_id), user)
    if b["demo"]:
        return {"businessId": business_id, "status": "complete", "demo": True}
    if not all(config.has_key(k) for k in pipeline.LIVE_KEYS):
        raise HTTPException(503, "Reports need ANTHROPIC_API_KEY and TAVILY_API_KEY in backend/.env.")
    report_id, already = reports.start(business_id)
    if not already:
        background.add_task(reports.run, business_id, report_id)
    return {"businessId": business_id, "status": "running", "reportId": report_id}


# ---------- alerts ----------

@router.get("/alerts")
def list_alerts(
    audience: Literal["consumer", "business"] = "consumer",
    businessId: str | None = Query(None, max_length=120),
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    radiusMi: float = Query(1.0, ge=0.1, le=5),
    cuisine: str | None = None,
    demo_flag: bool = Query(False, alias="demo"),
    user: dict | None = Depends(auth.current_user),
):
    if cuisine:
        _cuisine(cuisine)
    if audience == "business" and not businessId:
        raise HTTPException(400, "Business alerts need a businessId.")
    if audience == "consumer" and (lat is None or lng is None):
        lat, lng = config.CAPITOL_HILL["lat"], config.CAPITOL_HILL["lng"]
    business = store.get_business(businessId) if businessId else None
    if audience == "business" and business is not None:
        auth.check_owner(business, user)
    if audience == "business" and business is None and not _demo(demo_flag):
        raise HTTPException(404, "We couldn't find that business. Try onboarding it again.")
    if business and (lat is None or lng is None) and business["lat"] is not None:
        lat, lng = business["lat"], business["lng"]  # owners' distances are measured from their shop
    if _demo(demo_flag) or (business and business["demo"]):
        return demo.alerts(audience=audience, business_id=businessId, lat=lat, lng=lng, radius_mi=radiusMi, cuisine=cuisine)
    try:
        return alerts.list_alerts(audience=audience, lat=lat, lng=lng, radius_mi=radiusMi, business=business, cuisine=cuisine)
    except Exception:
        raise HTTPException(502, "Alerts aren't loading right now. Please try again in a minute.")


@router.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: str):
    if not alert_id or len(alert_id) > 120:
        raise HTTPException(400, "That alert id doesn't look right.")
    store.mark_read(alert_id)
    return {"ok": True}


def _refresh_alerts(business_id: str, monitor: bool, stock: bool) -> None:
    """Background: Ruth's monitor and the Square stock check. A failure in one doesn't stop the other."""
    if monitor:
        try:
            alerts.run_monitor(business_id)
        except Exception as e:
            store.update_business(business_id, scoring_error=f"Monitor: {str(e)[:250]}")
    if stock:
        try:
            alerts.check_stock(business_id)
        except Exception as e:
            store.update_business(business_id, scoring_error=f"Stock check: {str(e)[:250]}")


@router.post("/business/{business_id}/alerts/refresh")
def refresh_alerts(business_id: str, background: BackgroundTasks, monitor: bool = True, stock: bool = True,
                   user: dict | None = Depends(auth.current_user)):
    b = auth.check_owner(store.get_business(business_id), user)
    if b["demo"]:
        return {"status": "skipped", "demo": True}
    run_monitor = monitor and all(config.has_key(k) for k in pipeline.LIVE_KEYS)
    run_stock = stock and config.has_key("SQUARE_ACCESS_TOKEN")
    if not run_monitor and not run_stock:
        raise HTTPException(503, "Alert checks need ANTHROPIC_API_KEY and TAVILY_API_KEY (monitor) or SQUARE_ACCESS_TOKEN (stock) in backend/.env.")
    background.add_task(_refresh_alerts, business_id, run_monitor, run_stock)
    return {"status": "queued", "monitor": run_monitor, "stock": run_stock}
