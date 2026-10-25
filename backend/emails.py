"""Emails to business owners when Ruth's monitor finds competitor changes.

Sends through agent/notify.py (Resend when RESEND_API_KEY and RESEND_FROM are set, otherwise SMTP with
SMTP_USER and SMTP_PASSWORD). The recipient is the owner's sign-in email, recorded at onboarding. Every attempt
is written to the email_log table: sent, skipped (and why), or failed (with the error).
"""

import html
import os
from email.message import EmailMessage

import store

APP_URL = os.environ.get("APP_URL", "http://localhost:5173")


def _notify():
    from agent import notify
    return notify


def _html(business: dict, title: str, message: str) -> str:
    e = html.escape  # everything here can come from web pages or model output
    paragraphs = "".join(f'<p style="margin:0 0 12px">{e(p)}</p>' for p in message.split("\n") if p.strip())
    return f"""<!doctype html>
<html><body style="margin:0;background:#fff8e7;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#111">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%">
 <tr><td style="padding:0 0 12px;font-size:13px;font-weight:700;color:#9a6a12;letter-spacing:.06em;text-transform:uppercase">crumbs · {e(business['name'])}</td></tr>
 <tr><td style="padding:0 0 14px;font-size:22px;font-weight:800">{e(title)}</td></tr>
 <tr><td style="background:#fff;border:1px solid #ece4cf;border-radius:14px;padding:16px 18px;font-size:15px;line-height:1.55">{paragraphs}</td></tr>
 <tr><td style="padding:16px 0"><a href="{e(APP_URL)}/#/alerts" style="display:inline-block;background:#111;color:#fff;text-decoration:none;font-weight:700;padding:10px 18px;border-radius:999px">See your alerts</a></td></tr>
 <tr><td style="font-size:12px;color:#7a7262">You get this because you set up {e(business['name'])} on crumbs. Turn alert emails off in the app under You → Alert emails.</td></tr>
</table></td></tr></table></body></html>"""


def send_alert(business_id: str, title: str, message: str) -> str:
    """Email the owner a monitor alert. Returns the logged status: sent, skipped or failed. Never raises."""
    b = store.get_business(business_id)
    if b is None:
        return "skipped"
    subject = (title if b["name"] in title else f"{title} · {b['name']}")[:200]

    def log(status: str, detail: str | None = None) -> str:
        store.log_email(business_id, kind="monitor_alert", recipient=b.get("owner_email"), subject=subject,
                        status=status, detail=detail)
        return status

    if not b.get("email_alerts", 1):
        return log("skipped", "The owner turned alert emails off.")
    if not b.get("owner_email"):
        return log("skipped", "No owner email: the spot was set up without signing in.")
    notify = _notify()
    if not notify.email_configured():
        return log("skipped", "Email isn't set up on the server (RESEND_API_KEY + RESEND_FROM, or SMTP_USER + SMTP_PASSWORD).")
    try:
        msg = EmailMessage()
        msg["Subject"] = subject.replace("\n", " ")
        msg["From"] = os.environ.get("EMAIL_FROM") or os.environ.get("RESEND_FROM") or os.environ.get("SMTP_USER")
        msg["To"] = notify.validate_recipient(b["owner_email"])
        msg.set_content(f"{title}\n\n{message}\n\nSee your alerts: {APP_URL}/#/alerts")
        msg.add_alternative(_html(b, title, message), subtype="html")
        notify.send_email(msg)
    except Exception as e:
        return log("failed", str(e)[:300])
    return log("sent")
