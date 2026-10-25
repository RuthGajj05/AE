import config  # first: loads backend/.env before anything reads a key
import os
import uuid
from contextlib import asynccontextmanager
from typing import Dict
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import anthropic

from schemas import BusinessProfile, AnalyzeResponse
from analyzer import analyze
from demo_data import demo_report
from recommender import RecommendationsRequest, recommend, demo_tips

import demo
import scheduler
import store
from crumbs_api import router as crumbs_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    demo.seed()  # the demo business and its flagged sample picks
    scheduler.start()  # Mon/Wed/Fri competitor checks for app businesses (ALERT_SCHEDULE=off to disable)
    yield


app = FastAPI(title="Local Business Intel API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(crumbs_router)

RESULTS: Dict[str, AnalyzeResponse] = {}  # in-memory; fine for a one-day hackathon


@app.get("/api/health")
def health():
    # Which keys are set (never their values) and what's in the 24h cache.
    return {"ok": True, "demo_mode": config.demo_mode(), "has_key": config.has_key("ANTHROPIC_API_KEY"),
            "keys": {name: config.has_key(name) for name in config.KEY_NAMES},
            "squareEnvironment": os.getenv("SQUARE_ENVIRONMENT") or None,
            "scoringModel": config.SCORING_MODEL, "cache": store.cache_stats()}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze_business(profile: BusinessProfile, demo: bool = False):
    """Research nearby competitors + generate recommendations. Takes ~30-90s live; use ?demo=true to skip."""
    use_demo = demo or os.getenv("DEMO_MODE") == "1"
    try:
        report = demo_report(profile) if use_demo else analyze(profile)
    except anthropic.APIError as e:
        raise HTTPException(502, f"Claude API error: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))
    result = AnalyzeResponse(id=uuid.uuid4().hex[:8], profile=profile, report=report, demo=use_demo)
    RESULTS[result.id] = result
    return result


@app.get("/api/reports/{rid}", response_model=AnalyzeResponse)
def get_report(rid: str):
    if rid not in RESULTS:
        raise HTTPException(404, "report not found")
    return RESULTS[rid]


@app.post("/api/recommendations")
def recommendations(req: RecommendationsRequest, demo: bool = False):
    """Contract: frontend/API.md. Owner profile + competitors -> 3-6 ranked tips."""
    use_demo = demo or os.getenv("DEMO_MODE") == "1"
    try:
        tips = demo_tips(req) if use_demo else recommend(req)
    except anthropic.APIError as e:
        raise HTTPException(502, f"The AI service had a problem: {e}")
    return {"recommendations": [t.model_dump() for t in tips]}


# The frontend expects errors as {"error": "plain-English message"}.
@app.exception_handler(HTTPException)
async def http_err(_: Request, exc: HTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_err(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Some required details were missing or invalid."}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_err(_: Request, exc: Exception):
    return JSONResponse({"error": "Something went wrong on our side. Please try again."}, status_code=500)
