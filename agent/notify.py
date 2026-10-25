"""Email the advisor report to the business owner.

Two ways to send, picked from what is set in .env (Resend wins if both are set):

  Resend (the same keys the competitor alerts already use):
    RESEND_API_KEY, RESEND_FROM
    Note: Resend's test sender (onboarding@resend.dev) only delivers to your own account email;
    verify a domain in Resend to send to anyone.

  Plain SMTP, any provider; for Gmail use an app password:
    SMTP_HOST       default smtp.gmail.com
    SMTP_PORT       default 587 (STARTTLS)
    SMTP_USER       login, e.g. you@gmail.com
    SMTP_PASSWORD   an app password, never your real password
    EMAIL_FROM      optional; defaults to SMTP_USER

Usage (normally via advisor.py --email you@example.com):
    python agent/notify.py reports/test-bakery-2026-10-25-advisor.json you@example.com [--preview]
"""

import argparse
import html
import json
import os
import re
import smtplib
import sys

import httpx
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
ACCENT = "#c4441a"
CONFIDENCE_COLOR = {"high": "#1f7a3d", "medium": "#a8650a", "low": "#7b8a85"}


def validate_recipient(address: str) -> str:
    """One plain address only: rejects lists and anything that could inject mail headers."""
    address = address.strip()
    if not EMAIL_RE.match(address) or len(address) > 254:
        raise ValueError(f"Not a valid email address: {address!r}")
    return address


def _money(v: float | None) -> str:
    return f"~${v:,.0f}/mo" if v else "impact n/a"


def _total(recs: list[dict]) -> float:
    return sum(r.get("est_monthly_impact_usd") or 0 for r in recs)


def render_text(report: dict) -> str:
    a = report["advice"]
    recs = a["recommendations"]
    lines = [
        f"Your LocalEdge report: {report['business']} ({report['location']}), {report['date']}",
        "",
        a["snapshot"],
        "",
        f"What to do next ({len(recs)} tips, combined estimate {_money(_total(recs))}; estimates, not promises)",
        "",
    ]
    for i, r in enumerate(recs, 1):
        lines += [
            f"{i}. {r['title']} [{r['category']}, {_money(r.get('est_monthly_impact_usd'))}, {r['confidence']} confidence]",
            f"   Do this: {r['action']}",
            f"   Your data: {r['evidence_from_your_business']}",
            f"   The market: {r['evidence_from_market']}",
            f"   The math: {r['impact_math']}",
            "",
        ]
    if a["strengths"]:
        lines += ["Keep doing:"] + [f"- {s}" for s in a["strengths"]] + [""]
    if a["gaps_vs_competitors"]:
        lines += ["Where competitors beat you:"] + [f"- {s}" for s in a["gaps_vs_competitors"]] + [""]
    if a["caveats"]:
        lines += ["Limits of this data:"] + [f"- {s}" for s in a["caveats"]] + [""]
    lines.append("Dollar figures are estimates built from the assumptions shown. Check them against your own books.")
    return "\n".join(lines)


def _e(s: object) -> str:
    # Everything here can come from web pages or model output, so always escape it.
    return html.escape(str(s))


def render_html(report: dict) -> str:
    a = report["advice"]
    recs = a["recommendations"]
    cards = []
    for i, r in enumerate(recs, 1):
        color = CONFIDENCE_COLOR.get(r["confidence"], "#7b8a85")
        cards.append(f"""
<tr><td style="padding:0 0 14px">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eadfd2;border-radius:12px;border-left:5px solid {ACCENT};background:#ffffff">
  <tr><td style="padding:16px 18px">
   <div style="font-size:12px;color:#8f8478;text-transform:uppercase;letter-spacing:.06em">{i} · {_e(r['category'])}</div>
   <div style="font-size:17px;font-weight:700;color:#231c17;margin:2px 0 6px">{_e(r['title'])}</div>
   <div style="font-size:13px;margin-bottom:10px">
     <span style="background:#f3ece3;border-radius:999px;padding:2px 10px;color:#5b5148">{_e(_money(r.get('est_monthly_impact_usd')))}</span>
     <span style="color:{color};margin-left:8px;font-weight:600">{_e(r['confidence'])} confidence</span>
   </div>
   <div style="background:#fbf1ec;border-radius:8px;padding:10px 12px;font-size:14px;color:#231c17"><b style="color:{ACCENT};font-size:11px;text-transform:uppercase;letter-spacing:.06em">Do this</b><br>{_e(r['action'])}</div>
   <div style="font-size:13px;color:#5b5148;margin-top:10px"><b>Your data:</b> {_e(r['evidence_from_your_business'])}</div>
   <div style="font-size:13px;color:#5b5148;margin-top:6px"><b>The market:</b> {_e(r['evidence_from_market'])}</div>
   <div style="font-size:12px;color:#8f8478;margin-top:6px"><b>The math:</b> {_e(r['impact_math'])}</div>
  </td></tr>
 </table>
</td></tr>""")

    def bullets(title: str, items: list[str]) -> str:
        if not items:
            return ""
        li = "".join(f'<li style="margin-bottom:4px">{_e(x)}</li>' for x in items)
        return f'<tr><td style="padding:6px 0 10px"><div style="font-weight:700;color:#231c17;margin-bottom:6px">{_e(title)}</div><ul style="margin:0;padding-left:20px;font-size:14px;color:#5b5148">{li}</ul></td></tr>'

    return f"""<!doctype html>
<html><body style="margin:0;background:#faf6f1;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#231c17">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
 <tr><td style="padding:0 0 16px">
   <div style="font-size:13px;color:{ACCENT};font-weight:700;letter-spacing:.06em;text-transform:uppercase">LocalEdge</div>
   <div style="font-size:26px;font-weight:800;letter-spacing:-.02em;margin-top:4px">Your report is ready</div>
   <div style="font-size:14px;color:#5b5148;margin-top:2px">{_e(report['business'])} · {_e(report['location'])} · {_e(report['date'])}</div>
 </td></tr>
 <tr><td style="padding:0 0 16px"><div style="background:#ffffff;border:1px solid #eadfd2;border-radius:12px;padding:16px 18px;font-size:15px;line-height:1.55">{_e(a['snapshot'])}</div></td></tr>
 <tr><td style="padding:0 0 10px;font-size:18px;font-weight:700">What to do next
   <div style="font-size:13px;font-weight:400;color:#5b5148">{len(recs)} tips · combined estimate {_e(_money(_total(recs)))} (estimates, not promises)</div></td></tr>
 {''.join(cards)}
 {bullets('Keep doing', a['strengths'])}
 {bullets('Where competitors beat you', a['gaps_vs_competitors'])}
 {bullets('Limits of this data', a['caveats'])}
 <tr><td style="padding:14px 0 0;font-size:12px;color:#8f8478;border-top:1px solid #eadfd2">Dollar figures are estimates built from the assumptions shown. Check them against your own books before acting. You are receiving this because this address was entered for the report; we don't track opens or clicks.</td></tr>
</table></td></tr></table></body></html>"""


def build_email(report: dict, to: str, sender: str) -> EmailMessage:
    msg = EmailMessage()
    n = len(report["advice"]["recommendations"])
    msg["Subject"] = f"Your LocalEdge report for {report['business']}: {n} ways to earn more".replace("\n", " ")[:200]
    msg["From"] = sender
    msg["To"] = validate_recipient(to)
    msg.set_content(render_text(report))
    msg.add_alternative(render_html(report), subtype="html")
    return msg


def email_configured() -> bool:
    return bool(
        (os.environ.get("RESEND_API_KEY") and os.environ.get("RESEND_FROM"))
        or (os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))
    )


def _send_resend(msg: EmailMessage) -> None:
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": msg["From"],
            "to": [msg["To"]],
            "subject": msg["Subject"],
            "text": msg.get_body(("plain",)).get_content(),
            "html": msg.get_body(("html",)).get_content(),
        },
        timeout=30,
    )
    resp.raise_for_status()


def _send_smtp(msg: EmailMessage) -> None:
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)


def send_email(msg: EmailMessage) -> None:
    if os.environ.get("RESEND_API_KEY") and os.environ.get("RESEND_FROM"):
        _send_resend(msg)
    elif os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        _send_smtp(msg)
    else:
        raise RuntimeError("Email isn't configured: set RESEND_API_KEY and RESEND_FROM, or SMTP_USER and SMTP_PASSWORD, in .env (see README: Email).")


def email_report(report: dict, to: str, preview_dir: Path | None = None) -> str:
    """Send the report. With `preview_dir`, write the HTML there instead and send nothing."""
    sender = os.environ.get("EMAIL_FROM") or os.environ.get("RESEND_FROM") or os.environ.get("SMTP_USER") or "LocalEdge <noreply@localhost>"
    msg = build_email(report, to, sender)
    if preview_dir is not None:
        preview_dir.mkdir(exist_ok=True)
        out = preview_dir / "email-preview.html"
        out.write_text(msg.get_body(("html",)).get_content())
        return f"Preview written to {out} (nothing sent)"
    send_email(msg)
    return f"Report emailed to {msg['To']}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", help="Path to an advisor report JSON")
    parser.add_argument("to", help="Recipient email address")
    parser.add_argument("--preview", action="store_true", help="Write an HTML preview instead of sending")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text())
    print(email_report(report, args.to, Path("reports") if args.preview else None), file=sys.stderr)


if __name__ == "__main__":
    main()
