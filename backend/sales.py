"""Each business's sales connection: a CSV upload, Square, or Toast. Optional: without one, reports rest on
competitor research alone and carry no dollar estimates.

- CSV: the file is checked with Ruth's sales analysis and kept in backend/sales_uploads/ (gitignored).
- Square: the owner's access token (Square Developer dashboard), checked by listing its locations.
- Toast: the owner's Standard API access credentials (client id, secret, restaurant GUID), checked by logging in.

POS credentials are encrypted at rest (Fernet) with SALES_CREDENTIALS_KEY, or a key generated once into
backend/.sales_key, and are never sent back to the browser. A production version should use Square's OAuth
("Connect with Square") instead of pasted tokens.
"""

import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

import config
import store

UPLOAD_DIR = config.BACKEND_DIR / "sales_uploads"
KEY_FILE = config.BACKEND_DIR / ".sales_key"
SAMPLE_CSV = config.REPO_ROOT / "data" / "sample_sales.csv"
MAX_CSV_BYTES = 5 * 1024 * 1024
DAYS = 56
SOURCES = ("csv", "square", "toast")


def _agent():
    """Ruth's sales code (agent/pos.py and agent/business_agent.py)."""
    from agent import business_agent, pos
    return business_agent, pos


def _fernet() -> Fernet:
    key = os.environ.get("SALES_CREDENTIALS_KEY", "").strip()
    if not key:
        if not KEY_FILE.exists():
            KEY_FILE.write_bytes(Fernet.generate_key())
            KEY_FILE.chmod(0o600)
        key = KEY_FILE.read_text().strip()
    return Fernet(key.encode())


def _encrypt(secret: dict) -> str:
    return _fernet().encrypt(store._dump(secret).encode()).decode()


def _decrypt(token: str) -> dict:
    import json
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken:
        raise ValueError("The saved sales connection can't be read (the encryption key changed). Connect it again.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _csv_path(business_id: str) -> Path:
    return UPLOAD_DIR / f"{business_id}.csv"


def _summary(analysis: dict) -> dict:
    return {"period": analysis.get("period"), "items": len(analysis.get("items", [])),
            "daysWithSales": analysis.get("days_with_sales"), "totalRevenue": analysis.get("total_revenue")}


def status(business: dict) -> dict:
    """What the app shows: the source and its non-secret details. Never includes credentials."""
    source = business.get("sales_source")
    return {"connected": bool(source), "source": source, **(business.get("sales_meta") or {})}


def connect_csv(business_id: str, filename: str, text: str) -> dict:
    if len(text.encode()) > MAX_CSV_BYTES:
        raise ValueError("That file is over 5 MB. Export a shorter period, like the last 8 weeks.")
    business_agent, _ = _agent()
    import csv
    try:
        analysis = business_agent.analyze_rows(list(csv.DictReader(io.StringIO(text))), source="csv")
    except (KeyError, ValueError) as e:
        hint = (" It needs Date, Time, Item, Qty and Gross Sales columns, like Square's Items export."
                if isinstance(e, KeyError) else "")
        raise ValueError(f"We couldn't read that file: {str(e).strip(chr(39))}.{hint}")
    UPLOAD_DIR.mkdir(exist_ok=True)
    _csv_path(business_id).write_text(text)
    # The repo's fake sample sales keep their "demo" label, so a report never presents them as real.
    sample = SAMPLE_CSV.exists() and text.strip() == SAMPLE_CSV.read_text().strip()
    meta = {"label": (filename or "sales.csv")[:120], "connectedAt": _now(), "sample": sample, **_summary(analysis)}
    store.update_business(business_id, sales_source="csv", sales_meta=meta, sales_secret=None)
    return meta


def connect_square(business_id: str, token: str, environment: str) -> dict:
    _, pos = _agent()
    try:
        locations = pos.check_square(token.strip(), environment)
    except Exception:
        raise ValueError("Square didn't accept that access token. Check it, and that the environment "
                         "(sandbox or production) matches it.")
    if not locations:
        raise ValueError("That Square account has no locations.")
    location = locations[0]
    secret = {"token": token.strip(), "environment": environment, "location_id": location["id"]}
    meta = {"label": location["name"] or "Square", "environment": environment, "connectedAt": _now()}
    store.update_business(business_id, sales_source="square", sales_meta=meta, sales_secret=_encrypt(secret))
    _csv_path(business_id).unlink(missing_ok=True)
    return meta


def connect_toast(business_id: str, client_id: str, client_secret: str, guid: str) -> dict:
    _, pos = _agent()
    try:
        info = pos.check_toast(client_id.strip(), client_secret.strip(), guid.strip())
    except Exception:
        raise ValueError("Toast didn't accept those credentials. Check the client ID, secret and restaurant GUID "
                         "from Toast Web (Integrations → Toast API access).")
    secret = {"client_id": client_id.strip(), "client_secret": client_secret.strip(), "guid": guid.strip()}
    meta = {"label": info.get("name") or "Toast", "connectedAt": _now()}
    store.update_business(business_id, sales_source="toast", sales_meta=meta, sales_secret=_encrypt(secret))
    _csv_path(business_id).unlink(missing_ok=True)
    return meta


def disconnect(business_id: str) -> None:
    store.update_business(business_id, sales_source=None, sales_meta={}, sales_secret=None)
    _csv_path(business_id).unlink(missing_ok=True)


def analysis_for(business: dict) -> dict | None:
    """The business's sales analysis for its report, or None without a connection. Raises ValueError when the
    connection no longer works (e.g. a revoked token)."""
    source = business.get("sales_source")
    if not source:
        return None
    business_agent, pos = _agent()
    try:
        if source == "csv":
            sample = bool((business.get("sales_meta") or {}).get("sample"))
            return business_agent.analyze_sales(str(_csv_path(business["id"])), synthetic=sample)
        secret = _decrypt(business["sales_secret"])
        if source == "square":
            rows = pos.fetch_square(DAYS, token=secret["token"], environment=secret["environment"],
                                    location_id=secret.get("location_id"))
            return business_agent.analyze_rows(rows, source="square", environment=secret["environment"],
                                               synthetic=secret["environment"] == "sandbox")
        rows = pos.fetch_toast(DAYS, client_id=secret["client_id"], client_secret=secret["client_secret"],
                               guid=secret["guid"])
        return business_agent.analyze_rows(rows, source="toast")
    except ValueError:
        raise
    except Exception as e:
        print(f"[sales] {business['id']} {source}: {e}", file=sys.stderr)
        raise ValueError(f"We couldn't read your {source.capitalize()} sales. Reconnect it from the You tab.")
