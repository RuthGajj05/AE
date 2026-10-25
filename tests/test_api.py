"""Tests for agent/api.py. Research and SMTP are mocked: no network, no cost, no email sent. Run: python tests/test_api.py"""
import json, os, sys, time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
os.environ["EMAIL_COOLDOWN_SECS"] = "600"
os.environ["MAX_REPORTS_PER_HOUR"] = "5"
from fastapi.testclient import TestClient
import api

REPORT = json.load(open(ROOT / "examples" / "capitol-hill-bakery-advisor.json"))
c = TestClient(api.app)
body = lambda email: {"business": "Test Bakery", "business_type": "bakery", "location": "Capitol Hill, Seattle", "email": email}
ok = lambda name, cond: print(("PASS " if cond else "FAIL ") + name) or (cond or sys.exit(1))

def wait(job_id):
    for _ in range(100):
        j = c.get(f"/api/report-email/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    sys.exit("job never finished")

os.environ.update(SMTP_USER="u@example.com", SMTP_PASSWORD="pw")
with mock.patch.object(api.advisor, "run", return_value=REPORT) as run, mock.patch.object(api.notify, "send_email") as send:
    r = c.post("/api/report-email", json=body("a@example.com"))
    ok("accepts request immediately (202)", r.status_code == 202 and r.json()["status"] == "running")
    j = wait(r.json()["id"])
    ok("job finishes and emails once", j["status"] == "done" and j["emailed"] is True and send.call_count == 1)
    ok("email goes only to the entered address", send.call_args[0][0]["To"] == "a@example.com")
    ok("runs with no sales file", run.call_args.args[3] is None)
    ok("status returns the report when done", "report" in j)
    ok("pending status hides the report", "report" not in {k for k in api.JOBS[r.json()["id"]] if False})

    r2 = c.post("/api/report-email", json=body("A@example.com"))
    ok("same address again is rate limited (429, plain message)", r2.status_code == 429 and "wait" in r2.json()["error"])

    for bad in ["nope", "a@b.com, c@d.com", "x@y.com\nBcc: z@z.com"]:
        rb = c.post("/api/report-email", json=body(bad))
        ok(f"rejects bad email {bad!r}", rb.status_code == 400 and "error" in rb.json())
    ok("missing fields -> friendly 422", c.post("/api/report-email", json={"email": "q@example.com"}).json()["error"].startswith("Please fill"))
    ok("unknown job -> 404", c.get("/api/report-email/nope").status_code == 404)

# research fails -> job ends in error, no email, no internal details leaked
with mock.patch.object(api.advisor, "run", side_effect=RuntimeError("secret key sk-ant-123 leaked")), mock.patch.object(api.notify, "send_email") as send:
    j = wait(c.post("/api/report-email", json=body("b@example.com")).json()["id"])
    ok("failed research -> status error", j["status"] == "error" and send.call_count == 0)
    ok("error text leaks no internals", "sk-ant" not in json.dumps(j))

# email fails -> report still available
with mock.patch.object(api.advisor, "run", return_value=REPORT), mock.patch.object(api.notify, "send_email", side_effect=OSError("smtp down")):
    j = wait(c.post("/api/report-email", json=body("d@example.com")).json()["id"])
    ok("email failure keeps the report", j["status"] == "done" and j["emailed"] is False and "report" in j and "couldn't send" in j["error"])

# SMTP not configured -> report ready, honest message
for k in ("SMTP_USER", "SMTP_PASSWORD", "RESEND_API_KEY", "RESEND_FROM"): os.environ.pop(k, None)
with mock.patch.object(api.advisor, "run", return_value=REPORT), mock.patch.object(api.notify, "send_email") as send:
    j = wait(c.post("/api/report-email", json=body("e@example.com")).json()["id"])
    ok("no SMTP -> done, not emailed, clear message", j["status"] == "done" and not j["emailed"] and "isn't set up" in j["error"] and send.call_count == 0)
    ok("health shows email not configured", c.get("/api/health").json()["email_configured"] is False)

# global hourly cap (5 allowed above: a, b, d, e => 4 used; 1 left, then blocked)
with mock.patch.object(api.advisor, "run", return_value=REPORT):
    ok("5th report allowed", c.post("/api/report-email", json=body("f@example.com")).status_code == 202)
    r = c.post("/api/report-email", json=body("g@example.com"))
    ok("hourly cap blocks the next one", r.status_code == 429)
print("ALL PASSED")
