"""Supabase's REST API with the server key, for store.py only (tables: supabase/migrations/*_crumbs.sql).

On when SUPABASE_URL and a server key are set: SUPABASE_SERVICE_ROLE_KEY (a legacy service_role JWT or an sb_secret_
key) or SUPABASE_SECRET_KEY. The key bypasses row level security, so it stays in backend/.env, never in lovable-app/.
Same headers as Ruth's agent/supabase_store.py: sb_ keys go in apikey only, JWTs also in Authorization.

A failed write is logged and kept in `errors` instead of raised, so the local API keeps answering from SQLite;
scripts/sync_to_supabase.py checks `errors` and fails loudly.
"""

import os
import sys

import httpx

errors: list[str] = []
_client: httpx.Client | None = None


def url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def key() -> str:
    return (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.environ.get("SUPABASE_SECRET_KEY", "").strip())


def configured() -> bool:
    return bool(url() and key())


def use_client(client: httpx.Client | None) -> None:
    """Swap the HTTP client (tests pass one with a MockTransport)."""
    global _client
    _client = client


def _headers(prefer: str | None = None) -> dict:
    k = key()
    headers = {"apikey": k, "Content-Type": "application/json"}
    if not k.startswith("sb_"):
        headers["Authorization"] = f"Bearer {k}"
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=30)
    return _client


def _fail(what: str, e: Exception) -> None:
    detail = e.response.text[:200] if isinstance(e, httpx.HTTPStatusError) else str(e)
    errors.append(f"{what}: {detail}")
    print(f"[supabase] {what} failed: {detail}", file=sys.stderr)


def upsert(table: str, rows: dict | list[dict], *, on_conflict: str, ignore_duplicates: bool = False) -> bool:
    """Insert, or update the sent columns of an existing row (or leave it, with ignore_duplicates)."""
    rows = rows if isinstance(rows, list) else [rows]
    if not rows or not configured():
        return False
    resolution = "ignore-duplicates" if ignore_duplicates else "merge-duplicates"
    try:
        resp = _http().post(f"{url()}/rest/v1/{table}", params={"on_conflict": on_conflict}, json=rows,
                            headers=_headers(f"resolution={resolution},return=minimal"))
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        _fail(f"upsert {table}", e)
        return False


def insert(table: str, rows: dict | list[dict]) -> bool:
    rows = rows if isinstance(rows, list) else [rows]
    if not rows or not configured():
        return False
    try:
        resp = _http().post(f"{url()}/rest/v1/{table}", json=rows, headers=_headers("return=minimal"))
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        _fail(f"insert {table}", e)
        return False


def update(table: str, filters: dict, fields: dict) -> bool:
    """PATCH every row matching PostgREST filters, e.g. {"cuisine": "eq.sushi"}."""
    if not configured():
        return False
    try:
        resp = _http().patch(f"{url()}/rest/v1/{table}", params=filters, json=fields, headers=_headers("return=minimal"))
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        _fail(f"update {table}", e)
        return False


def select(table: str, params: dict) -> list[dict] | None:
    """Rows, or None when Supabase is off or the read failed (callers fall back to SQLite)."""
    if not configured():
        return None
    try:
        resp = _http().get(f"{url()}/rest/v1/{table}", params=params, headers=_headers())
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as e:
        _fail(f"select {table}", e)
        return None
