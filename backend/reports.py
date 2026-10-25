"""Tailored advisor reports for onboarded businesses, from Ruth's advisor (agent/advisor.py).

A report runs in the background (about a minute): sales analysis when Square is connected, competitor research
(one agent per nearby competitor), the owner's online presence, product gaps, then recommendations. The full
report is kept in SQLite and, when the business is linked to Ruth's Supabase project, in its advisor_reports too.
"""

import json
from datetime import datetime, timedelta, timezone

import alerts
import config
import cuisines
import sales as sales_data
import store

# A report still "running" after this long is treated as abandoned (e.g. the server restarted mid-run).
STALE_RUNNING = timedelta(minutes=15)
EXAMPLE_REPORT = config.REPO_ROOT / "examples" / "capitol-hill-bakery-advisor.json"


def _advisor():
    from agent import advisor
    return advisor


def _running(business_id: str) -> dict | None:
    latest = store.latest_report(business_id)
    if latest and latest["status"] == "running":
        started = datetime.fromisoformat(latest["created_at"])
        if datetime.now(timezone.utc) - started < STALE_RUNNING:
            return latest
    return None


def start(business_id: str) -> tuple[str, bool]:
    """Record a new running report. Returns (report id, already_running): one report per business at a time."""
    running = _running(business_id)
    if running:
        return running["id"], True
    return store.start_report(business_id), False


def run(business_id: str, report_id: str) -> None:
    """Background job: research and write the report. Never raises; a failure is stored as a plain-English error."""
    b = store.get_business(business_id)
    if b is None:
        store.finish_report(report_id, error="We couldn't find that business.")
        return
    sales_problem = None
    try:
        analysis = sales_data.analysis_for(b)
    except ValueError as e:  # e.g. a revoked token: still write the report, and say why it has no sales
        analysis, sales_problem = None, str(e)
    try:
        report = _advisor().run(
            b["name"], cuisines.research_type(b), b["location"], None, b.get("website"),
            reports_dir=config.REPO_ROOT / "reports", sales=analysis,
        )
    except Exception as e:
        store.finish_report(report_id, error=f"The research didn't finish: {str(e)[:250]}")
        return
    if sales_problem:
        report.setdefault("advice", {}).setdefault("caveats", []).insert(0, sales_problem)
    supabase_id = None
    if alerts.supabase_configured() and b.get("supabase_business_id"):
        try:
            sb = alerts._supabase()
            supabase_id = sb.save_advisor_report(sb.get_business(b["supabase_business_id"]), report)
        except Exception as e:  # the local copy still counts; note the failed copy
            report.setdefault("advice", {}).setdefault("caveats", []).append(f"Not copied to Supabase: {str(e)[:120]}")
    store.finish_report(report_id, data=report, supabase_report_id=supabase_id)


def example_report() -> dict:
    """The saved Capitol Hill bakery report, for demo businesses and demo mode."""
    return json.loads(EXAMPLE_REPORT.read_text())


def summary(report: dict) -> dict:
    """The compact view the app's Report tab shows; the full report rides along for the dashboard."""
    advice = report.get("advice") or {}
    competitors = (report.get("competitors") or {}).get("competitors") or []
    gaps = ((report.get("market_intelligence") or {}).get("product_gaps")) or []
    sales = report.get("your_sales") or {}
    return {
        "business": report.get("business"),
        "location": report.get("location"),
        "date": report.get("date"),
        "isDemoSales": bool(sales.get("is_synthetic")),
        "usedSales": bool(sales.get("items")),
        "snapshot": advice.get("snapshot"),
        "recommendations": [{
            "title": r.get("title"),
            "category": r.get("category"),
            "action": r.get("action"),
            "evidenceYours": r.get("evidence_from_your_business"),
            "evidenceMarket": r.get("evidence_from_market"),
            "monthlyImpactUsd": r.get("est_monthly_impact_usd"),
            "impactMath": r.get("impact_math"),
            "confidence": r.get("confidence"),
        } for r in advice.get("recommendations") or []],
        "strengths": advice.get("strengths") or [],
        "gapsVsCompetitors": advice.get("gaps_vs_competitors") or [],
        "caveats": advice.get("caveats") or [],
        "productGaps": [{
            "product": g.get("product"),
            "competitorCount": g.get("competitor_count"),
            "competitors": [c.get("business_name") for c in g.get("competitors") or []],
            "needsConfirmation": g.get("owner_menu_status") != "confirmed_absent",
        } for g in gaps],
        "competitors": [{
            "name": c.get("name"),
            "address": c.get("address"),
            "rating": c.get("rating"),
            "reviewCount": c.get("review_count"),
            "hours": c.get("hours"),
            "pricePoints": c.get("price_points") or [],
        } for c in competitors],
    }


def view(business_id: str, *, demo: bool = False) -> dict:
    """GET /api/business/{id}/report: the latest report's status, plus its summary and full JSON when there is one."""
    base = {"businessId": business_id, "demo": demo}
    if demo:
        report = example_report()
        return {**base, "status": "complete", "error": None, "reportId": "demo", "createdAt": report.get("date"),
                "summary": summary(report), "report": report}
    latest = store.latest_report(business_id)
    if latest is None:
        return {**base, "status": "none", "error": None, "reportId": None, "summary": None, "report": None}
    if latest["status"] == "running" and _running(business_id) is None:
        latest = {**latest, "status": "failed", "error": "The research stopped before finishing. Please try again."}
    # While a new report runs (or after one fails), keep showing the last complete one.
    shown = latest if latest["status"] == "complete" else store.latest_report(business_id, complete_only=True)
    data = (shown or {}).get("data")
    return {**base, "status": latest["status"], "error": latest["error"], "reportId": latest["id"],
            "createdAt": (shown or latest)["created_at"], "summary": summary(data) if data else None, "report": data}
