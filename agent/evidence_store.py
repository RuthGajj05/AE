"""Source provenance for one live run and business-scoped report history."""

import hashlib
import json
import re
import threading
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import ValidationError

try:
    from .market_intelligence import EvidenceBundle
except ImportError:
    from market_intelligence import EvidenceBundle


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def blocked_url(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)


class SourceLedger:
    """Keep only text actually returned to Claude, never unseen full-page text."""

    def __init__(self):
        self._lock = threading.Lock()
        self.records: dict[str, list[dict]] = {}
        self.failures: list[dict] = []

    def clear(self):
        with self._lock:
            self.records.clear()
            self.failures.clear()

    def add(self, url: str, content: str, kind: str, **metadata):
        if not url or not content:
            return
        with self._lock:
            self.records.setdefault(url, []).append(
                {"content": content, "kind": kind, **metadata}
            )

    def fail(self, url: str, error: str):
        with self._lock:
            self.failures.append({"url": url, "error": error})

    def coverage(self) -> dict:
        with self._lock:
            return {
                "sources": [
                    {"url": url, "retrieval_kinds": sorted({r["kind"] for r in records})}
                    for url, records in sorted(self.records.items())
                ],
                "failed_extractions": list(self.failures),
                "note": "A retrieved page or listing count is not a count of collected reviews.",
            }

    def validate(self, bundle: EvidenceBundle, branches: set[tuple[str, str]]) -> EvidenceBundle:
        """Reject invented sources, cross-branch records and upgraded search snippets.

        Extracted pages can still contain editorial summaries: the classifier must
        label those honestly. Imports are a separate explicit, user-supplied path.
        """
        today = date.today()
        for item in [*bundle.menu_observations, *bundle.review_observations]:
            if (normalized(item.business_name), normalized(item.address)) not in branches:
                raise ValueError(f"Evidence branch is not in competitors: {item.business_name}, {item.address}")
            if item.source_url not in self.records:
                raise ValueError(f"Evidence source was not retrieved in this run: {item.source_url}")

        for item in bundle.menu_observations:
            records = self.records[item.source_url]
            if not any(
                r["kind"] == "page_text" and normalized(item.product) in normalized(r["content"])
                for r in records
            ):
                raise ValueError(f"Menu item must appear verbatim on an extracted page: {item.product}")
            item.observed_at = today

        for item in bundle.review_observations:
            records = [
                r for r in self.records[item.source_url]
                if normalized(item.text) in normalized(r["content"])
            ]
            expected = {
                "review_text": {"page_text"}, "editorial": {"page_text", "search_snippet"},
                "search_snippet": {"search_snippet", "page_text"},
                "google_places_sample": {"google_places_sample"},
            }[item.source_kind]
            records = [r for r in records if r["kind"] in expected]
            if not records:
                raise ValueError(f"Review text/kind is not supported by retrieved content: {item.source_url}")
            if item.source_kind == "google_places_sample":
                records = [r for r in records if (
                    normalized(r.get("business_name", "")) == normalized(item.business_name)
                    and normalized(r.get("address", "")) == normalized(item.address)
                )]
                if not records:
                    raise ValueError("Google review does not match the exact returned branch")
            if item.published_at:
                day = item.published_at
                date_strings = {day.isoformat(), day.strftime("%B %d, %Y"),
                                f"{day:%B} {day.day}, {day.year}",
                                f"{day.day} {day:%B %Y}", day.strftime("%b %d, %Y")}
                if not any(
                    r.get("published_at") == day.isoformat()
                    or (r["kind"] == "page_text" and any(s in r["content"] for s in date_strings))
                    for r in records
                ):
                    raise ValueError("Publication date is not explicit in the source; use null, not retrieval date")
                if day > today:
                    raise ValueError("Review publication date cannot be in the future")
            item.observed_at = today
        return bundle


def business_key(business: str, location: str) -> str:
    return hashlib.sha256(f"{normalized(business)}\n{normalized(location)}".encode()).hexdigest()[:12]


def load_history(directory: Path, business: str, location: str, as_of: date,
                 mode: str | None = None) -> tuple[list[EvidenceBundle], list[str]]:
    bundles, warnings = [], []
    key = business_key(business, location)
    for path in sorted(directory.glob(f"*-{key}-*.json")):
        try:
            report = json.loads(path.read_text())
            if business_key(report["business"], report["location"]) != key:
                continue
            if mode is not None and report.get("mode") != mode:
                warnings.append(f"Skipped history from a different collection mode: {path.name}")
                continue
            # Avoid leaking a later run's observations into a historical analysis.
            if date.fromisoformat(report.get("analysis_date", report["date"])) > as_of:
                continue
            if "evidence_bundle" in report:
                bundles.append(EvidenceBundle.model_validate(report["evidence_bundle"]))
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            warnings.append(f"Skipped invalid history file {path.name}: {type(exc).__name__}")
    return bundles, warnings


def save_report(report: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w]+", "-", report["business"].casefold()).strip("-")[:60] or "business"
    key = business_key(report["business"], report["location"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"{slug}-{key}-{stamp}-{uuid4().hex[:8]}.json"
    with path.open("x") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return path
