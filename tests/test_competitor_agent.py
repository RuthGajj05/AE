"""Integration boundaries: provenance, selected samples and offline CLI safety."""

import json
import copy
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import competitor_agent as agent
from agent import agent_loop
from agent.evidence_store import SourceLedger, load_history, normalized, save_report
from agent.market_intelligence import EvidenceBundle, OwnerMenu, analyze_market


ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.com/bakery/reviews"
BRANCH = ("Example Bakery", "10 Example Avenue, Seattle")
BRANCHES = {(normalized(BRANCH[0]), normalized(BRANCH[1]))}


def review(**changes):
    value = {
        "business_name": BRANCH[0], "address": BRANCH[1],
        "source_url": URL, "text": "I enjoyed the croissant.",
        "source_kind": "review_text", "published_at": None,
    }
    value.update(changes)
    return value


class SourceProvenanceTests(unittest.TestCase):
    def setUp(self):
        agent.ledger.clear()

    def test_search_snippet_cannot_be_promoted_to_full_review(self):
        client = Mock()
        client.search.return_value = {"results": [{
            "title": "Bakery feedback", "url": URL,
            "content": "I enjoyed the croissant.",
        }]}
        with patch.object(agent, "tavily_client", return_value=client):
            result = json.loads(agent.search_web.call({"query": "bakery reviews"}))
        self.assertEqual(result[0]["source_kind"], "search_snippet")
        with self.assertRaisesRegex(ValueError, "text/kind"):
            agent.ledger.validate(EvidenceBundle(review_observations=[review()]), BRANCHES)
        accepted = agent.ledger.validate(EvidenceBundle(review_observations=[
            review(source_kind="search_snippet")
        ]), BRANCHES)
        self.assertEqual(accepted.review_observations[0].source_kind, "search_snippet")

    def test_only_page_content_visible_to_model_can_support_evidence(self):
        client = Mock()
        client.extract.return_value = {
            "results": [{"url": URL, "raw_content": "x" * agent.MAX_PAGE_CHARS + "Hidden tart"}],
            "failed_results": [{"url": "https://example.com/failed", "error": "Unavailable"}],
        }
        with patch.object(agent, "tavily_client", return_value=client):
            result = json.loads(agent.read_pages.call({"urls": [URL]}))
        self.assertIn("[truncated:", result[0]["content"])
        self.assertNotIn("Hidden tart", result[0]["content"])
        self.assertEqual(agent.ledger.coverage()["failed_extractions"][0]["error"], "Unavailable")
        bundle = EvidenceBundle(menu_observations=[{
            "business_name": BRANCH[0], "address": BRANCH[1], "source_url": URL,
            "product": "Hidden tart", "observed_at": date.today(),
        }])
        with self.assertRaisesRegex(ValueError, "verbatim"):
            agent.ledger.validate(bundle, BRANCHES)

    def test_unknown_sources_and_cross_branch_evidence_are_rejected(self):
        ledger = SourceLedger()
        with self.assertRaisesRegex(ValueError, "not retrieved"):
            ledger.validate(EvidenceBundle(review_observations=[review()]), BRANCHES)
        ledger.add(URL, "I enjoyed the croissant.", "page_text")
        with self.assertRaisesRegex(ValueError, "branch"):
            ledger.validate(EvidenceBundle(review_observations=[
                review(address="99 Other Branch Avenue, Seattle")
            ]), BRANCHES)

    def test_date_cannot_be_invented_from_collection_time(self):
        ledger = SourceLedger()
        ledger.add(URL, "I enjoyed the croissant.", "page_text")
        with self.assertRaisesRegex(ValueError, "Publication date"):
            ledger.validate(EvidenceBundle(review_observations=[
                review(published_at="2026-09-10")
            ]), BRANCHES)
        ledger.add(URL, "September 10, 2026\nI enjoyed the croissant.", "page_text")
        accepted = ledger.validate(EvidenceBundle(review_observations=[
            review(published_at="2026-09-10")
        ]), BRANCHES)
        self.assertEqual(accepted.review_observations[0].published_at, date(2026, 9, 10))

    def test_menu_requires_extracted_text_instead_of_search_snippet(self):
        ledger = SourceLedger()
        ledger.add(URL, "Croissant", "search_snippet")
        bundle = EvidenceBundle(menu_observations=[{
            "business_name": BRANCH[0], "address": BRANCH[1], "source_url": URL,
            "product": "Croissant", "observed_at": "2000-01-01",
        }])
        with self.assertRaisesRegex(ValueError, "extracted page"):
            ledger.validate(bundle, BRANCHES)
        ledger.add(URL, "Croissant", "page_text")
        accepted = ledger.validate(bundle, BRANCHES)
        self.assertEqual(accepted.menu_observations[0].observed_at, date.today())

    def test_google_review_is_selected_sample_with_stable_id_and_date(self):
        response = {
            "id": "place-1", "displayName": {"text": BRANCH[0]},
            "formattedAddress": BRANCH[1], "googleMapsUri": URL,
            "rating": 4.6, "userRatingCount": 900,
            "reviews": [{
                "name": "places/place-1/reviews/review-1", "rating": 5,
                "relativePublishTimeDescription": "a month ago",
                "publishTime": "2026-09-10T10:00:00Z",
                "text": {"text": "I enjoyed the croissant."},
                "authorAttribution": {"displayName": "Example customer"},
            }],
        }
        with patch.object(agent, "_places_request", return_value=response):
            result = json.loads(agent.get_place_reviews.call({"place_id": "place-1"}))
        self.assertEqual(result["review_count"], 900)
        self.assertEqual(len(result["reviews"]), 1)
        self.assertEqual(result["reviews"][0]["published_at"], "2026-09-10")
        self.assertEqual(result["reviews"][0]["review_id"], "places/place-1/reviews/review-1")
        self.assertEqual(result["reviews"][0]["source_kind"], "google_places_sample")
        self.assertIn("relevance-selected", result["sampling_note"])
        with self.assertRaisesRegex(ValueError, "text/kind"):
            agent.ledger.validate(EvidenceBundle(review_observations=[review()]), BRANCHES)
        accepted = agent.ledger.validate(EvidenceBundle(review_observations=[
            review(source_kind="google_places_sample", published_at="2026-09-10")
        ]), BRANCHES)
        self.assertEqual(accepted.review_observations[0].source_kind, "google_places_sample")

    def test_google_source_does_not_transfer_to_another_allowed_branch(self):
        ledger = SourceLedger()
        ledger.add(URL, "I enjoyed the croissant.", "google_places_sample",
                   business_name=BRANCH[0], address=BRANCH[1])
        other = "99 Other Branch Avenue, Seattle"
        branches = BRANCHES | {(normalized(BRANCH[0]), normalized(other))}
        with self.assertRaisesRegex(ValueError, "exact returned branch"):
            ledger.validate(EvidenceBundle(review_observations=[
                review(source_kind="google_places_sample", address=other)
            ]), branches)


class OfflineCliTests(unittest.TestCase):
    # The fresh interpreter disables dotenv, all client constructors and sockets.
    # This catches a future accidental request even if the environment has keys.
    BOOTSTRAP = """
import runpy, socket, sys
import anthropic, dotenv, tavily
def forbidden(*args, **kwargs):
    raise AssertionError('Offline mode attempted an API client or network connection')
class ForbiddenClient:
    def __init__(self, *args, **kwargs):
        forbidden()
dotenv.load_dotenv = lambda *args, **kwargs: False
anthropic.Anthropic = ForbiddenClient
tavily.TavilyClient = ForbiddenClient
socket.socket.connect = forbidden
socket.create_connection = forbidden
sys.argv = ['agent/competitor_agent.py', *sys.argv[1:]]
runpy.run_path('agent/competitor_agent.py', run_name='__main__')
"""

    def offline(self, directory):
        env = {key: value for key, value in os.environ.items()
               if key not in {"ANTHROPIC_API_KEY", "TAVILY_API_KEY", "GOOGLE_PLACES_API_KEY"}}
        # run_path uses the standalone script imports, just as python script.py.
        env["PYTHONPATH"] = str(ROOT / "agent")
        return subprocess.run([
            sys.executable, "-c", self.BOOTSTRAP,
            "Synthetic Example Bakery", "bakery", "10 Demo Lane, Seattle",
            "--evidence", str(ROOT / "examples/product-opportunity-demo.json"),
            "--owner-menu", str(ROOT / "examples/demo-owner-menu.json"),
            "--as-of", "2026-10-25", "--reports-dir", str(directory),
        ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)

    def test_offline_cli_needs_no_clients_and_preserves_repeat_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            first = self.offline(directory)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = next(directory.glob("*.json"))
            original_bytes = original.read_bytes()
            second = self.offline(directory)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(original.read_bytes(), original_bytes)
            reports = [json.loads(path.read_text()) for path in directory.glob("*.json")]
            self.assertEqual(len(reports), 2)
            self.assertEqual(sorted(r["history_reports_used"] for r in reports), [0, 1])
            by_history = sorted(reports, key=lambda r: r["history_reports_used"])
            for report in reports:
                self.assertEqual(report["mode"], "imported_evidence")
                self.assertTrue(report["market_intelligence"]["product_gaps"])
            self.assertEqual(by_history[0]["market_intelligence"]["product_trends"],
                             by_history[1]["market_intelligence"]["product_trends"])
            self.assertEqual(by_history[0]["evidence_bundle"], by_history[1]["evidence_bundle"])

    def test_live_run_reports_missing_keys_before_creating_clients(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(agent_loop.anthropic, "Anthropic", side_effect=AssertionError("client created")):
            with self.assertRaisesRegex(ValueError, "ANTHROPIC_API_KEY"):
                agent.run("Example Bakery", "bakery", "Seattle")

    def test_imported_history_cannot_influence_live_analysis(self):
        evidence = json.loads((ROOT / "examples/product-opportunity-demo.json").read_text())
        owner = OwnerMenu.model_validate_json((ROOT / "examples/demo-owner-menu.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            save_report({
                "business": "Real Bakery", "location": "Seattle",
                "mode": "imported_evidence", "date": "2026-10-25",
                "analysis_date": "2026-10-25", "evidence_bundle": evidence,
                "gaps_and_caveats": ["Synthetic demo input"],
            }, directory)
            result = agent.analyze_report({
                "business": "Real Bakery", "location": "Seattle",
                "mode": "live_research", "date": "2026-10-25",
                "evidence_bundle": {}, "source_coverage": {"sources": []},
            }, owner, reports_dir=directory, as_of=date(2026, 10, 25))
        self.assertEqual(result["history_reports_used"], 0)
        self.assertEqual(result["market_intelligence"]["product_gaps"], [])
        self.assertEqual(result["market_intelligence"]["product_trends"], [])
        self.assertTrue(result["gaps_and_caveats"], "Skipped imported history should be visible")

    def test_portable_analysis_evidence_reproduces_history_based_trends(self):
        evidence = json.loads((ROOT / "examples/product-opportunity-demo.json").read_text())
        owner = OwnerMenu.model_validate_json((ROOT / "examples/demo-owner-menu.json").read_text())
        previous = [item for item in evidence["review_observations"]
                    if item.get("published_at") and item["published_at"] < "2026-09-26"]
        current = [item for item in evidence["review_observations"] if item not in previous]
        self.assertTrue(previous)
        self.assertTrue(current)

        def report(bundle):
            return {
                "business": "Synthetic Example Bakery", "location": "10 Demo Lane, Seattle",
                "mode": "imported_evidence", "date": "2026-10-25", "analysis_date": "2026-10-25",
                "evidence_bundle": bundle,
            }

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            past_bundle = {"menu_observations": [], "review_observations": previous}
            # Identical repeated history snapshots must not bloat the portable input.
            save_report(report(past_bundle), directory)
            save_report(report(past_bundle), directory)
            current_bundle = {"menu_observations": evidence["menu_observations"], "review_observations": current}
            result = agent.analyze_report(report(current_bundle), owner, reports_dir=directory, as_of=date(2026, 10, 25))
            portable = result["analysis_evidence_bundle"]
            unique_observations = {item.model_dump_json() for item in EvidenceBundle.model_validate(evidence).review_observations}
            self.assertEqual(len(portable["review_observations"]), len(unique_observations))
            self.assertEqual(len(result["evidence_bundle"]["review_observations"]), len(current))
            self.assertTrue(any(trend["status"] == "rising" for trend in result["market_intelligence"]["product_trends"]))
            reproduced = analyze_market(
                result["business"], result["location"], owner_menu=result["owner_menu"], evidence=portable,
                as_of=date.fromisoformat(result["analysis_date"]),
                window_days=result["market_intelligence"]["window_days"],
                min_reviews_per_period=result["market_intelligence"]["min_reviews_per_period"],
            ).model_dump(mode="json")
            self.assertEqual(reproduced, result["market_intelligence"])
            save_report(result, directory)
            history, warnings = load_history(directory, result["business"], result["location"], date(2026, 10, 25), mode="imported_evidence")
            self.assertEqual(warnings, [])
            self.assertEqual(sum(len(bundle.review_observations) for bundle in history), 2 * len(previous) + len(current))


class ParallelResearchTests(unittest.TestCase):
    def test_two_runs_isolate_sources_clients_and_reports_with_parallel_retrieval(self):
        # Four retrievals must reach the barrier before any can finish: two
        # independent requests per run, with both business runs active together.
        barrier = Barrier(4, timeout=5)
        clients = []
        validations = []
        lock = Lock()
        original_validate = SourceLedger.validate

        class FakeTavily:
            def __init__(self, **kwargs):
                self.businesses = []
                with lock:
                    clients.append(self)

            def search(self, query, **kwargs):
                with lock:
                    self.businesses.append(query)
                barrier.wait()
                return {"results": [{
                    "url": f"https://example.com/{query}/reviews",
                    "title": f"{query} feedback", "content": f"I enjoyed the {query} croissant.",
                }]}

            def extract(self, urls, **kwargs):
                business = urls[0].split("/")[-2]
                with lock:
                    self.businesses.append(business)
                barrier.wait()
                return {"results": [{"url": urls[0], "raw_content": f"{business} croissant"}]}

        class FakeAnthropic:
            def __init__(self):
                self.calls = 0
                self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

            def create(self, messages, **kwargs):
                self.calls += 1
                if self.calls != 1:
                    raise AssertionError("The first turn should submit a validated report")
                business = messages[0]["content"].splitlines()[0].removeprefix("Business: ")
                name, address = f"{business} competitor", f"{business} Street, Seattle"
                menu_url = f"https://example.com/{business}/menu"
                submission = {
                    "competitors": [{"name": name, "address": address, "hours": "Daily 7am–5pm"}],
                    "gaps_and_caveats": [],
                    "menu_observations": [{
                        "business_name": name, "address": address, "source_url": menu_url,
                        "product": f"{business} croissant", "observed_at": date.today().isoformat(),
                    }],
                    "review_observations": [{
                        "business_name": name, "address": address,
                        "source_url": f"https://example.com/{business}/reviews",
                        "text": f"I enjoyed the {business} croissant.", "source_kind": "search_snippet",
                    }],
                }

                def call(name, inputs):
                    return SimpleNamespace(type="tool_use", id=f"{business}-{name}", name=name, input=inputs)

                # Put submit first deliberately. It must still run after both
                # retrievals, otherwise its source validation will reject it.
                return SimpleNamespace(stop_reason="tool_use", content=[
                    call("submit_report", submission),
                    call("search_web", {"query": business}),
                    call("read_pages", {"urls": [menu_url]}),
                ])

        def validate(ledger, bundle, branches):
            result = original_validate(ledger, bundle, branches)
            with lock:
                validations.append(set(ledger.records))
            return result

        agent.ledger.clear()
        agent.submitted.clear()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unused-test", "TAVILY_API_KEY": "unused-test"}), \
             patch.object(agent_loop.anthropic, "Anthropic", FakeAnthropic), \
             patch.object(agent, "TavilyClient", FakeTavily), \
             patch.object(agent, "GOOGLE_PLACES_API_KEY", None), \
             patch.object(SourceLedger, "validate", validate), \
             ThreadPoolExecutor(max_workers=2) as outer:
            futures = [outer.submit(agent.run, business, "bakery", f"{business} area", max_workers=2, strategy="single")
                       for business in ("alpha", "beta")]
            reports = [future.result(timeout=10) for future in futures]

        self.assertEqual(len(clients), 2, "Each run should lazily create exactly one client")
        self.assertEqual(sorted(sorted(client.businesses) for client in clients),
                         [["alpha", "alpha"], ["beta", "beta"]])
        self.assertEqual(len(validations), 2)
        for report in reports:
            business = report["business"]
            expected = {f"https://example.com/{business}/menu", f"https://example.com/{business}/reviews"}
            self.assertEqual(report["competitors"][0]["name"], f"{business} competitor")
            self.assertEqual(report["competitors"][0]["hours"], "Daily 7am–5pm")
            self.assertEqual(report["mode"], "live_research")
            self.assertNotIn("market_summary", report)
            self.assertNotIn("insights", report)
            self.assertEqual({source["url"] for source in report["source_coverage"]["sources"]}, expected)
            self.assertIn(expected, validations)
            self.assertEqual(report["evidence_bundle"]["menu_observations"][0]["product"],
                             f"{business} croissant")
        self.assertEqual(agent.ledger.records, {}, "Live runs must not mutate direct-tool state")
        self.assertEqual(agent.submitted, {})
        self.assertIsNone(agent._active_session.get())

    def test_max_workers_is_validated_before_api_clients(self):
        with patch.object(agent_loop.anthropic, "Anthropic", side_effect=AssertionError("client created")):
            for value in (0, 11, -1, 1.5, True):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "max_workers"):
                    agent.run("Example", "bakery", "Seattle", max_workers=value)

    def test_session_is_reset_if_model_fails(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unused-test", "TAVILY_API_KEY": "unused-test"}), \
             patch.object(agent_loop.anthropic, "Anthropic", side_effect=RuntimeError("simulated model failure")):
            with self.assertRaisesRegex(RuntimeError, "simulated model failure"):
                agent.run("Example", "bakery", "Seattle", strategy="single")
        self.assertIsNone(agent._active_session.get())


class BackendApiTests(unittest.TestCase):
    def test_submit_schema_remains_facts_only_with_upstream_hours(self):
        properties = agent.submit_report.to_dict()["input_schema"]["properties"]
        self.assertEqual(set(properties), {"competitors", "gaps_and_caveats", "menu_observations", "review_observations"})
        self.assertIn("hours", agent.Competitor.model_fields)
        self.assertIn("place_types", agent.find_nearby_osm.to_dict()["input_schema"]["properties"])

    def test_research_returns_json_and_optionally_saves_mode_compatible_history(self):
        evidence = json.loads((ROOT / "examples/product-opportunity-demo.json").read_text())
        base = {
            "business": "Example Bakery", "type": "bakery", "location": "Seattle",
            "date": date.today().isoformat(), "mode": "live_research",
            "competitors": [], "gaps_and_caveats": [], "evidence_bundle": evidence,
            "source_coverage": {"sources": []},
        }
        with tempfile.TemporaryDirectory() as temp, patch.object(agent, "run", side_effect=lambda *a, **k: copy.deepcopy(base)) as collect:
            directory = Path(temp) / "reports"
            unsaved = agent.research("Example Bakery", "bakery", "Seattle", {"products": ["Coffee"]},
                                     reports_dir=directory, use_history=False, save=False, window_days=14, min_reviews=6)
            self.assertFalse(directory.exists())
            self.assertEqual(unsaved["mode"], "live_research")
            self.assertEqual(unsaved["market_intelligence"]["window_days"], 14)
            self.assertEqual(unsaved["market_intelligence"]["min_reviews_per_period"], 6)
            self.assertIsInstance(collect.call_args.args[3], OwnerMenu)
            first = agent.research("Example Bakery", "bakery", "Seattle", reports_dir=directory)
            second = agent.research("Example Bakery", "bakery", "Seattle", reports_dir=directory)
            self.assertEqual(first["history_reports_used"], 0)
            self.assertEqual(second["history_reports_used"], 1)
            self.assertEqual(len(list(directory.glob("*.json"))), 2)
            self.assertEqual(json.loads(json.dumps(second)), second)
            self.assertIn("analysis_evidence_bundle", second)
            self.assertNotIn("report_path", second)

    def test_bad_analysis_options_fail_before_paid_research(self):
        with patch.object(agent, "run", side_effect=AssertionError("live research started")):
            for options in ({"window_days": 0}, {"window_days": 366}, {"window_days": True}, {"min_reviews": 0}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    agent.research("Example", "bakery", "Seattle", **options)

    def test_research_session_is_lazy_and_does_not_require_keys(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(agent, "TavilyClient", side_effect=AssertionError("client created")):
            with agent.research_session() as session:
                self.assertIsNone(session.tavily)
                self.assertIs(agent._source_ledger(), session.ledger)
                with self.assertRaisesRegex(ValueError, "TAVILY_API_KEY"):
                    agent.tavily_client()
        self.assertIsNone(agent._active_session.get())


class NominatimCacheTests(unittest.TestCase):
    def test_corrupt_cache_is_replaced_and_concurrent_same_query_is_fetched_once(self):
        params = {"q": "Example Bakery", "limit": 1}
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        started, release = Event(), Event()
        data = [{"lat": "47.0", "lon": "-122.0"}]
        response = Mock()
        response.json.return_value = data

        def request(*args, **kwargs):
            started.set()
            if not release.wait(timeout=5):
                raise AssertionError("Cache test did not release its request")
            return response

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            cache = directory / f"{key}.json"
            cache.write_text('{"interrupted":')
            with patch.object(agent, "OSM_CACHE_DIR", directory), \
                 patch.object(agent, "_nominatim_last", [0.0]), \
                 patch.object(agent.httpx, "get", side_effect=request) as fetch, \
                 ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(agent._nominatim, params)
                self.assertTrue(started.wait(timeout=5))
                second = pool.submit(agent._nominatim, params)
                release.set()
                self.assertEqual(first.result(timeout=5), data)
                self.assertEqual(second.result(timeout=5), data)
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(agent._nominatim(params), data)
                self.assertEqual(fetch.call_count, 1)
            self.assertEqual(json.loads(cache.read_text()), data)
            self.assertEqual(list(directory.glob("*.tmp")), [])

    def test_failed_request_still_advances_rate_limit_timestamp(self):
        last = [0.0]
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(agent, "OSM_CACHE_DIR", Path(temp)), \
             patch.object(agent, "_nominatim_last", last), \
             patch.object(agent.time, "monotonic", side_effect=[100.0, 101.0]), \
             patch.object(agent.httpx, "get", side_effect=RuntimeError("connection failed")):
            with self.assertRaisesRegex(RuntimeError, "connection failed"):
                agent._nominatim({"q": "Example"})
        self.assertEqual(last[0], 101.0)


if __name__ == "__main__":
    unittest.main()
