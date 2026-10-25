from typing import List, Optional
from pydantic import BaseModel, Field


class BusinessProfile(BaseModel):
    name: str
    category: str = Field(description="e.g. bakery, ramen shop, coffee shop")
    neighborhood: str = Field(description="e.g. Capitol Hill, Seattle")
    avg_price: Optional[str] = Field(None, description="typical item/meal price, e.g. '$14'")
    avg_wait_minutes: Optional[int] = None
    notes: Optional[str] = Field(None, description="anything else the owner wants considered")


class Competitor(BaseModel):
    name: str
    address: Optional[str] = None
    price_range: Optional[str] = None
    typical_wait: Optional[str] = None
    rating: Optional[str] = None
    strengths: List[str] = []
    customer_complaints: List[str] = []
    source_urls: List[str] = []


class Recommendation(BaseModel):
    title: str
    detail: str
    area: str = Field(description="one of: pricing, wait_times, service, marketing, menu, other")
    impact: str = Field(description="high | medium | low")
    evidence: str = Field(description="what in the competitor data supports this")


class AnalysisReport(BaseModel):
    summary: str
    competitors: List[Competitor]
    market_trends: List[str]
    pricing_position: str = Field(description="where the business sits vs. nearby competitors")
    recommendations: List[Recommendation]
    caveats: str = Field(description="honest limits of the data (small sample, stale pages, etc.)")


class AnalyzeResponse(BaseModel):
    id: str
    profile: BusinessProfile
    report: AnalysisReport
    demo: bool = False
