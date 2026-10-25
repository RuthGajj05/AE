"""POST /api/recommendations: owner profile + competitors -> ranked tips (contract: frontend/API.md)."""
import json
import os
import statistics
from typing import Any, Dict, List, Literal, Optional

import anthropic
from pydantic import BaseModel, ConfigDict, Field

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")


class Profile(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    category: str
    neighborhood: str = ""
    reviewUrl: Optional[str] = ""
    rating: Optional[float] = None
    reviewCount: Optional[int] = None
    itemPrice: Optional[float] = None
    waitMin: Optional[float] = None


class RecommendationsRequest(BaseModel):
    profile: Profile
    competitors: List[Dict[str, Any]] = []


class Tip(BaseModel):
    id: str
    title: str = Field(description="One plain-English line")
    evidence: str = Field(description="Real numbers from the provided data only")
    action: str = Field(description="One concrete thing to try this week")
    impact: Literal["high", "medium", "low"]
    effort: Literal["high", "medium", "low"]


class TipsOut(BaseModel):
    recommendations: List[Tip]


SYSTEM = (
    "You advise busy owners of small neighborhood shops who are not technical. Write 3-6 tips, "
    "ranked best first (high impact and low effort first). Use ONLY numbers present in the data "
    "you are given; never invent figures, and never promise specific savings or revenue. "
    "Every tip's evidence must cite concrete numbers (owner's value vs. nearby median, counts, "
    "percentages). Treat null/missing values as unknown and do not mention them as facts. "
    "If there are too few competitors to conclude anything, say so in the evidence. "
    "Ids are short unique kebab-case strings."
)


def _num(v) -> Optional[float]:
    try:
        return float(str(v).replace("$", "").replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _median(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 2) if vals else None


def compute_stats(req: RecommendationsRequest) -> dict:
    """Precompute medians in code so the model quotes numbers instead of doing arithmetic."""
    comps = req.competitors
    complaints: Dict[str, int] = {}
    for c in comps:
        for k, n in (c.get("complaints") or {}).items():
            n = _num(n)
            if n:
                complaints[k] = complaints.get(k, 0) + int(n)
    raised = [c for c in comps if (_num(c.get("priceChange90d")) or 0) > 0]
    return {
        "competitor_count": len(comps),
        "median_item_price": _median(_num(c.get("itemPrice")) for c in comps),
        "median_wait_min": _median(_num(c.get("waitMin")) for c in comps),
        "median_rating": _median(_num(c.get("rating")) for c in comps),
        "competitors_that_raised_price_90d": len(raised),
        "competitors_with_price_change_data": sum(1 for c in comps if _num(c.get("priceChange90d")) is not None),
        "total_complaint_mentions_by_theme": dict(sorted(complaints.items(), key=lambda kv: -kv[1])),
    }


def recommend(req: RecommendationsRequest, trends: Optional[List[str]] = None) -> List[Tip]:
    client = anthropic.Anthropic()
    payload = {
        "owner": req.profile.model_dump(exclude={"reviewUrl"}),
        "computed_stats": compute_stats(req),
        "competitors": req.competitors,
    }
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": json.dumps(payload, indent=1)}],
        output_format=TipsOut,
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"No recommendations returned (stop_reason={resp.stop_reason})")
    return resp.parsed_output.recommendations


def demo_tips(req: RecommendationsRequest) -> List[Tip]:
    s = compute_stats(req)
    return [Tip(
        id="demo-wait", title="Promote your short wait", impact="high", effort="low",
        evidence=f"[DEMO] {s['competitor_count']} competitors nearby; median wait {s['median_wait_min']} min.",
        action="Mention your fast service on your Google listing this week.",
    )]
