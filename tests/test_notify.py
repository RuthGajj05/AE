"""Tests for agent/notify.py. No network: SMTP is mocked. Run: python tests/test_notify.py"""
import copy, json, os, sys
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import notify

report = json.load(open(Path(__file__).resolve().parent.parent / "examples" / "capitol-hill-bakery-advisor.json"))
ok = lambda name, cond: print(("PASS " if cond else "FAIL ") + name) or (cond or sys.exit(1))

# 1. content + both parts
msg = notify.build_email(report, "owner@example.com", "LocalEdge <me@example.com>")
ok("has text and html parts", msg.get_body(("plain",)) and msg.get_body(("html",)))
ok("subject mentions business", "Test Bakery" in msg["Subject"])
text = msg.get_body(("plain",)).get_content()
ok("text lists all recommendations", all(r["title"] in text for r in report["advice"]["recommendations"]))

# 2. HTML escaping of web/model-derived text
evil = copy.deepcopy(report)
evil["business"] = "<img src=x onerror=alert(1)>"
evil["advice"]["recommendations"][0]["title"] = "<script>alert('x')</script>"
h = notify.render_html(evil)
ok("script tag escaped", "<script>" not in h and "&lt;script&gt;" in h)
ok("img tag escaped", "<img src=x" not in h)

# 3. recipient validation (header injection, lists)
for bad in ["a@b.com\nBcc: x@y.com", "a@b.com, c@d.com", "nope", "a@b", "<a@b.com>"]:
    try: notify.validate_recipient(bad); ok(f"rejects {bad!r}", False)
    except ValueError: ok(f"rejects {bad!r}", True)

# 4. sending path with a fake SMTP server
os.environ.update(SMTP_USER="u@example.com", SMTP_PASSWORD="app-pass", SMTP_HOST="smtp.test", SMTP_PORT="587")
with mock.patch("smtplib.SMTP") as smtp:
    out = notify.email_report(report, "owner@example.com")
    s = smtp.return_value.__enter__.return_value
    ok("connects to configured host", smtp.call_args[0][:2] == ("smtp.test", 587))
    ok("uses STARTTLS before login", [c[0] for c in s.method_calls][:2] == ["starttls", "login"])
    ok("logs in with env creds", s.login.call_args[0] == ("u@example.com", "app-pass"))
    sent = s.send_message.call_args[0][0]
    ok("sent to the owner only", sent["To"] == "owner@example.com" and not sent["Bcc"] and not sent["Cc"])
    ok("reports success", "emailed to owner@example.com" in out)

# 5. missing credentials -> clear error, nothing sent
for k in ("SMTP_USER", "SMTP_PASSWORD"): os.environ.pop(k)
with mock.patch("smtplib.SMTP") as smtp:
    try: notify.email_report(report, "owner@example.com"); ok("errors without creds", False)
    except RuntimeError as e: ok("errors without creds (clear message)", "SMTP_USER" in str(e) and not smtp.called)

# 6. preview mode writes a file and sends nothing
with mock.patch("smtplib.SMTP") as smtp:
    print(notify.email_report(report, "owner@example.com", Path("reports")))
    ok("preview sends nothing", not smtp.called)
print("ALL PASSED")
