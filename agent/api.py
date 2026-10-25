"""Small standalone API: a user enters their business and email, the report is researched in the
background and emailed when ready.

Run:  .venv/bin/uvicorn api:app --app-dir agent --port 8100

POST /api/report-email   {business, business_type, location, email, website?}  -> 202 {id, status}
GET  /api/report-email/{id}                                                    -> {status, emailed, error, report?}
GET  /api/health

Errors are {"error": "plain-English message"}. Since this can spend API credit and send email, there are
limits: one report per address per EMAIL_COOLDOWN_SECS (default 600) and MAX_REPORTS_PER_HOUR overall (default 30).
"""

import json
import os
import re
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import advisor
import competitor_agent
import notify

COOLDOWN_SECS = int(os.environ.get("EMAIL_COOLDOWN_SECS", "600"))
MAX_PER_HOUR = int(os.environ.get("MAX_REPORTS_PER_HOUR", "30"))

app = FastAPI(title="LocalEdge report API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_pool = ThreadPoolExecutor(max_workers=3)  # each job already runs many threads internally
_lock = threading.Lock()
JOBS: dict[str, dict] = {}
_last_by_email: dict[str, float] = {}
_recent: deque[float] = deque()


class ReportRequest(BaseModel):
    business: str = Field(min_length=1, max_length=100)
    business_type: str = Field(min_length=1, max_length=60, description="e.g. bakery")
    location: str = Field(min_length=1, max_length=100, description="e.g. Capitol Hill, Seattle")
    email: str
    website: str | None = Field(None, max_length=200)


def _check_limits(email: str) -> None:
    now = time.time()
    with _lock:
        while _recent and now - _recent[0] > 3600:
            _recent.popleft()
        if len(_recent) >= MAX_PER_HOUR:
            raise HTTPException(429, "We're busy right now. Please try again in a little while.")
        wait = COOLDOWN_SECS - (now - _last_by_email.get(email, 0))
        if wait > 0:
            raise HTTPException(429, f"A report for this address was just requested. Please wait about {int(wait // 60) + 1} minute(s).")
        _recent.append(now)
        _last_by_email[email] = now


def _run_job(job_id: str, req: ReportRequest, email: str) -> None:
    job = JOBS[job_id]
    try:
        report = advisor.run(req.business, req.business_type, req.location, None, req.website)
    except Exception as e:  # report the failure; never leave a job "running" forever
        job.update(status="error", error="We couldn't finish the research this time. Please try again.")
        print(f"[api] job {job_id} research failed: {e}")
        return
    competitor_agent.REPORTS_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", req.business.lower()).strip("-") or "business"
    (competitor_agent.REPORTS_DIR / f"{slug}-{job_id}-advisor.json").write_text(json.dumps(report, indent=2))
    # "done" is set only after the email attempt, so a status check never sees done-but-not-yet-emailed.
    emailed, error = False, None
    if not notify.email_configured():
        error = "The report is ready, but email isn't set up on this server."
    else:
        try:
            notify.email_report(report, email)
            emailed = True
        except Exception as e:
            error = "The report is ready, but we couldn't send the email."
            print(f"[api] job {job_id} email failed: {e}")
    job.update(status="done", report=report, emailed=emailed, error=error)  # the report is kept even if the email failed


@app.post("/api/report-email", status_code=202)
def request_report(req: ReportRequest):
    try:
        email = notify.validate_recipient(req.email)
    except ValueError:
        raise HTTPException(400, "That email address doesn't look right.")
    _check_limits(email.lower())
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {"status": "running", "emailed": False, "error": None, "started": time.time()}
    _pool.submit(_run_job, job_id, req, email)
    return {"id": job_id, "status": "running", "message": "We're researching your market. We'll email the report when it's ready (about a minute)."}


@app.get("/api/report-email/{job_id}")
def report_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "We couldn't find that report.")
    return {k: v for k, v in job.items() if k != "started" and not (k == "report" and job["status"] != "done")}


@app.get("/api/health")
def health():
    return {"ok": True, "email_configured": notify.email_configured()}


@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Please fill in your business name, type, area and email."}, status_code=422)
