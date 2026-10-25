import os
import uuid
from typing import Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import anthropic

from schemas import BusinessProfile, AnalyzeResponse
from analyzer import analyze
from demo_data import demo_report

app = FastAPI(title="Local Business Intel API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

RESULTS: Dict[str, AnalyzeResponse] = {}  # in-memory; fine for a one-day hackathon


@app.get("/api/health")
def health():
    return {"ok": True, "demo_mode": os.getenv("DEMO_MODE") == "1",
            "has_key": bool(os.getenv("ANTHROPIC_API_KEY"))}


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
