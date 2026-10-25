"""Supabase storage for the monitor (tables in supabase/migrations/).

Talks to Supabase's REST API with the service-role key, which bypasses row
level security, so keep SUPABASE_SERVICE_ROLE_KEY server-side only (never in
the Lovable frontend).

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx


class SupabaseStore:
    def __init__(self, url: str | None = None, key: str | None = None, http: httpx.Client | None = None):
        url = url or os.environ.get("SUPABASE_URL")
        key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not (url and key):
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        self.http = http or httpx.Client(timeout=30)
        self.base = f"{url.rstrip('/')}/rest/v1"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if not key.startswith("sb_"):
            # Legacy service_role keys are JWTs and also go in Authorization;
            # newer sb_secret_ keys go in the apikey header only.
            self.headers["Authorization"] = f"Bearer {key}"

    # ---------- low-level REST helpers ----------

    def _get(self, table: str, params: dict) -> list[dict]:
        resp = self.http.get(f"{self.base}/{table}", params=params, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def _insert(self, table: str, rows: dict | list[dict], upsert_on: str | None = None) -> list[dict]:
        headers = {**self.headers, "Prefer": "return=representation"}
        params = {}
        if upsert_on:
            headers["Prefer"] += ",resolution=merge-duplicates"
            params["on_conflict"] = upsert_on
        resp = self.http.post(f"{self.base}/{table}", json=rows, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _update(self, table: str, row_id: str, fields: dict) -> None:
        resp = self.http.patch(
            f"{self.base}/{table}", params={"id": f"eq.{row_id}"}, json=fields, headers=self.headers,
        )
        resp.raise_for_status()

    # ---------- businesses ----------

    def monitored_businesses(self) -> list[dict]:
        return self._get("businesses", {"monitor_enabled": "is.true", "select": "*"})

    def get_business(self, business_id: str) -> dict:
        rows = self._get("businesses", {"id": f"eq.{business_id}", "select": "*"})
        if not rows:
            raise RuntimeError(f"No business with id {business_id}")
        return rows[0]

    # ---------- monitor runs ----------

    def start_run(self, business: dict) -> str:
        return self._insert("monitor_runs", {"business_id": business["id"]})[0]["id"]

    def finish_run(self, run_id: str, *, error: str | None = None, changes: int = 0, baseline: bool = False) -> None:
        self._update("monitor_runs", run_id, {
            "finished_at": _now(),
            "status": "failed" if error else "succeeded",
            "error": error,
            "changes_count": changes,
            "is_baseline": baseline,
        })

    # ---------- snapshots and competitors ----------

    def latest_snapshot(self, business: dict) -> dict | None:
        rows = self._get("snapshots", {
            "business_id": f"eq.{business['id']}", "order": "taken_at.desc", "limit": 1, "select": "id,data",
        })
        return {**rows[0]["data"], "_id": rows[0]["id"]} if rows else None

    def save_snapshot(self, business: dict, data: dict, run_id: str | None) -> str:
        snapshot_id = self._insert("snapshots", {
            "business_id": business["id"], "run_id": run_id, "data": data,
        })[0]["id"]
        now = _now()
        competitors = [{
            "business_id": business["id"],
            "name": c["name"],
            "address": c.get("address"),
            "website": c.get("website"),
            "rating": c.get("rating"),
            "review_count": c.get("review_count"),
            "hours": c.get("hours"),
            "status": c.get("status"),
            "details": c,
            "last_seen_at": now,
        } for c in data.get("competitors", [])]
        if competitors:
            # first_seen_at keeps its default on insert and isn't sent, so upserts don't overwrite it
            self._insert("competitors", competitors, upsert_on="business_id,name")
        return snapshot_id

    # ---------- changes and notifications ----------

    def save_changes(self, business: dict, changes: list[dict], run_id: str | None,
                     snapshot_id: str, previous_snapshot_id: str | None) -> None:
        if not changes:
            return
        self._insert("changes", [{
            "business_id": business["id"], "run_id": run_id,
            "snapshot_id": snapshot_id, "previous_snapshot_id": previous_snapshot_id,
            "kind": c["kind"], "competitor_name": c["competitor"], "before": c["before"],
            "after": c["after"], "evidence": c["evidence"], "why_it_matters": c["why_it_matters"],
        } for c in changes])

    def queue_notifications(self, business: dict, title: str, message: str, run_id: str | None) -> None:
        """Add the alert to the in-app feed now, and queue a text/email for the owner's notify hour."""
        now = _now()
        send_after = next_notify_time(business.get("timezone") or "UTC", business.get("notify_hour", 14))

        def row(channel: str, status: str, when: str, sent_at: str | None) -> dict:
            # Supabase's bulk insert requires every row to have the same keys.
            return {"business_id": business["id"], "run_id": run_id, "channel": channel, "title": title,
                    "message": message, "status": status, "send_after": when, "sent_at": sent_at}

        rows = [row("in_app", "sent", now, now)]
        if business.get("sms_opt_in") and business.get("sms_phone"):
            rows.append(row("sms", "pending", send_after, None))
        if business.get("email_opt_in") and business.get("email"):
            rows.append(row("email", "pending", send_after, None))
        self._insert("notifications", rows)

    def due_notifications(self) -> list[dict]:
        return self._get("notifications", {
            "status": "eq.pending",
            "send_after": f"lte.{_now()}",
            "channel": "in.(sms,email)",
            "select": "*,businesses(name,sms_phone,sms_opt_in,email,email_opt_in)",
            "order": "send_after.asc",
        })

    def mark_notification(self, notification_id: str, status: str, error: str | None = None) -> None:
        fields = {"status": status, "error": error}
        if status == "sent":
            fields["sent_at"] = _now()
        self._update("notifications", notification_id, fields)

    # ---------- advisor reports ----------

    def save_advisor_report(self, business: dict, report: dict) -> str:
        return self._insert("advisor_reports", {
            "business_id": business["id"],
            "advice": report["advice"],
            "sales_summary": report.get("your_sales"),
            "online_presence": report.get("your_online_presence"),
            "competitors": report.get("competitors"),
        })[0]["id"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_notify_time(tz_name: str, hour: int, now: datetime | None = None) -> str:
    """The next time it's `hour`:00 in the owner's time zone (or now, during that hour), in UTC."""
    tz = ZoneInfo(tz_name)
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    if local.hour == hour:
        target = local
    else:
        target = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target < local:
            target += timedelta(days=1)
    return target.astimezone(timezone.utc).isoformat()
