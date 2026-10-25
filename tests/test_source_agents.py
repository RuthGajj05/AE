"""Independent source specialists, enforced scopes and deterministic evidence merge."""

import copy
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from datetime import date
from threading import Barrier, Event, Lock
from unittest.mock import Mock, patch

from agent import competitor_agent as ca
from agent import source_agents as sa
from agent.evidence_store import normalized
from agent.market_intelligence import EvidenceBundle, OwnerMenu, analyze_market


BRANCH = {"name": "Nearby Bakery", "address": "2 Main Street, Seattle", "website": "https://trusted.example/"}
BRANCH_KEY = (normalized(BRANCH["name"]), normalized(BRANCH["address"]))
TEST_CALL = ContextVar("source_agent_test_call", default="unset")


def facts(*, rating=None, review_count=None, hours=None, reviews=None):
    return {
        "competitors": [{**BRANCH, "rating": rating, "review_count": review_count, "hours": hours,
                         "specialties": [], "price_points": [], "praised_for": [], "complaints": [], "sources": []}],
        "gaps_and_caveats": [],
        "evidence_bundle": {"menu_observations": [], "review_observations": reviews or []},
    }


def completed(agent_id, report=None):
    report = report or facts()
    return {"report": report, "run": {
        "id": agent_id, "status": "complete", "error": None, "elapsed_seconds": 0,
        "competitor_count": len(report["competitors"]),
        "menu_observation_count": len(report["evidence_bundle"]["menu_observations"]),
        "review_observation_count": len(report["evidence_bundle"]["review_observations"]),
        "source_coverage": {"sources": [], "failed_extractions": []},
    }}


def scope(**overrides):
    values = {"agent_id": "test_source", "allowed_domains": ("trusted.example",),
              "allowed_branches": frozenset({BRANCH_KEY})}
    values.update(overrides)
    return ca.SourceScope(**values)


class SourceScopeTests(unittest.TestCase):
    def test_search_enforces_domain_filters_and_rejects_returned_lookalikes(self):
        client = Mock()
        client.search.return_value = {"results": [
            {"url": "https://trusted.example/reviews", "content": "Allowed", "title": "Good"},
            {"url": "https://orders.trusted.example/menu", "content": "Allowed subdomain", "title": "Good"},
            {"url": "https://trusted.example.attacker.test/reviews", "content": "Wrong", "title": "Bad"},
            {"url": "https://other.example/reviews", "content": "Wrong", "title": "Bad"},
            {"url": "https://blocked.trusted.example/reviews", "content": "Blocked", "title": "Bad"},
        ]}
        with ca.research_session(scope(excluded_domains=("blocked.trusted.example",))) as session, \
             patch.object(ca, "tavily_client", return_value=client):
            result = json.loads(ca.search_web.call({"query": "site:other.example croissant", "purpose": "reviews"}))
            self.assertEqual({item["url"] for item in result}, {"https://trusted.example/reviews", "https://orders.trusted.example/menu"})
            self.assertEqual(set(session.ledger.records), {item["url"] for item in result})
        self.assertEqual(client.search.call_args.kwargs["include_domains"], ["trusted.example"])
        self.assertIn("blocked.trusted.example", client.search.call_args.kwargs["exclude_domains"])

    def test_extract_filters_inputs_and_returned_redirect_domains(self):
        client = Mock()
        client.extract.return_value = {"results": [
            {"url": "https://trusted.example/menu", "raw_content": "Croissant"},
            {"url": "https://other.example/redirect", "raw_content": "Unrelated menu"},
        ]}
        with ca.research_session(scope()) as session, patch.object(ca, "tavily_client", return_value=client):
            result = json.loads(ca.read_pages.call({"urls": ["https://other.example/menu", "https://trusted.example/menu"]}))
            self.assertEqual(client.extract.call_args.kwargs["urls"], ["https://trusted.example/menu"])
            self.assertEqual([item["url"] for item in result if "content" in item], ["https://trusted.example/menu"])
            self.assertEqual(set(session.ledger.records), {"https://trusted.example/menu"})

    def test_review_only_and_empty_domain_scopes_never_extract_or_search_elsewhere(self):
        with ca.research_session(scope(allow_page_reads=False)), patch.object(ca, "tavily_client") as client:
            ca.read_pages.call({"urls": ["https://trusted.example/reviews"]})
            client.assert_not_called()
        with ca.research_session(scope(allowed_domains=())), patch.object(ca, "tavily_client") as client:
            ca.search_web.call({"query": "anything"})
            client.assert_not_called()

    def test_search_budget_is_reserved_across_parallel_workers(self):
        client = Mock()
        client.search.return_value = {"results": [{"url": "https://trusted.example/reviews", "content": "A review", "title": "Reviews"}]}
        with ca.research_session(scope(max_searches=1)), patch.object(ca, "tavily_client", return_value=client), ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(copy_context().run, ca.search_web.call, {"query": f"query {i}"}) for i in range(2)]
            results = [call.result(timeout=5) for call in calls]
        self.assertEqual(client.search.call_count, 1)
        self.assertEqual(sum("https://trusted.example/reviews" in result for result in results), 1)

    def test_specialist_cannot_submit_an_undiscovered_branch_even_without_observations(self):
        with ca.research_session(scope()):
            ca.submit_report.call({"competitors": [BRANCH], "gaps_and_caveats": []})
        with ca.research_session(scope()):
            with self.assertRaises(ValueError):
                ca.submit_report.call({"competitors": [{**BRANCH, "address": "99 Another Branch, Seattle"}], "gaps_and_caveats": []})

    def test_specialist_cannot_cite_an_out_of_scope_domain_in_summary_sources(self):
        with ca.research_session(scope()):
            with self.assertRaises(ValueError):
                ca.submit_report.call({"competitors": [{**BRANCH, "sources": ["https://other.example/reviews"]}], "gaps_and_caveats": []})

    def test_non_google_specialist_cannot_call_google_places(self):
        with ca.research_session(scope(allow_google_places=False)), \
             patch.object(ca, "GOOGLE_PLACES_API_KEY", "test-placeholder"), \
             patch.object(ca.httpx, "request") as request:
            ca.find_places.call({"query": "Nearby Bakery Seattle"})
            ca.get_place_reviews.call({"place_id": "outside-place"})
            request.assert_not_called()


class MultiSourceSchedulingTests(unittest.TestCase):
    def test_source_agents_overlap_and_respect_max_agents(self):
        active, peak = 0, 0
        entered, extra, release, lock = Event(), Event(), Event(), Lock()
        jobs = []

        def specialist(profile, *args, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                jobs.append(profile.id)
                if active == 2:
                    entered.set()
                if active > 2:
                    extra.set()
            try:
                if not release.wait(timeout=5):
                    raise AssertionError("Parallel scheduling test did not release agents")
                self.assertEqual(kwargs["max_workers"], 1)
                return completed(profile.id)
            finally:
                with lock:
                    active -= 1

        with patch.object(sa, "_run_discovery", return_value=completed("discovery")), \
             patch.object(sa, "_run_specialist", side_effect=specialist), \
             patch.object(ca, "GOOGLE_PLACES_API_KEY", "test-placeholder"), ThreadPoolExecutor(max_workers=1) as outer:
            run = outer.submit(sa.run_multi_source, "Owner", "bakery", "Seattle", max_workers=1, max_agents=2)
            try:
                self.assertTrue(entered.wait(timeout=5), "Two independent specialists should start together")
                self.assertFalse(extra.wait(timeout=0.1), "max_agents must cap active specialists")
            finally:
                release.set()
            result = run.result(timeout=5)
        self.assertEqual(peak, 2)
        self.assertGreaterEqual(len(jobs), 3)
        self.assertTrue(any(item["status"] == "complete" for item in result["agent_runs"]))

    def test_one_source_failure_keeps_other_results_and_sanitizes_error(self):
        def specialist(profile, *args, **kwargs):
            if profile.id == "yelp_reviews":
                raise RuntimeError("PRIVATE_API_TOKEN_should_never_be_returned")
            return completed(profile.id, facts(rating=4.5))

        with patch.object(sa, "_run_discovery", return_value=completed("discovery")), \
             patch.object(sa, "_run_specialist", side_effect=specialist), patch.object(ca, "GOOGLE_PLACES_API_KEY", None):
            result = sa.run_multi_source("Owner", "bakery", "Seattle", max_agents=2)
        self.assertTrue(result["competitors"])
        runs = {item["id"]: item for item in result["agent_runs"]}
        self.assertEqual(runs["yelp_reviews"]["status"], "failed")
        self.assertEqual(runs["official_menus"]["status"], "complete")
        self.assertEqual(runs["google_reviews"]["status"], "complete")
        self.assertEqual(result["collection_status"], "partial")
        self.assertNotIn("PRIVATE_API_TOKEN", json.dumps(result))

    def test_missing_official_websites_skips_that_agent_without_broadening_its_scope(self):
        discovery = facts()
        discovery["competitors"][0]["website"] = None
        attempted = []
        def specialist(profile, *args, **kwargs):
            attempted.append(profile.id)
            return completed(profile.id, discovery)

        with patch.object(sa, "_run_discovery", return_value=completed("discovery", discovery)), \
             patch.object(sa, "_run_specialist", side_effect=specialist):
            result = sa.run_multi_source("Owner", "bakery", "Seattle", max_agents=2)
        self.assertNotIn("official_menus", attempted)
        official = next(item for item in result["agent_runs"] if item["id"] == "official_menus")
        self.assertEqual(official["status"], "skipped")
        self.assertEqual(result["collection_status"], "partial")

    def test_all_attempted_specialists_failing_does_not_look_like_a_successful_report(self):
        with patch.object(sa, "_run_discovery", return_value=completed("discovery")), \
             patch.object(sa, "_run_specialist", side_effect=RuntimeError("failed")), \
             patch.object(ca, "GOOGLE_PLACES_API_KEY", None):
            with self.assertRaises(RuntimeError):
                sa.run_multi_source("Owner", "bakery", "Seattle", max_agents=2)

    def test_invalid_agent_count_fails_before_discovery(self):
        with patch.object(sa, "_run_discovery") as discover:
            for max_agents in (0, 7, True, 1.5):
                with self.subTest(max_agents=max_agents), self.assertRaises(ValueError):
                    sa.run_multi_source("Owner", "bakery", "Seattle", max_agents=max_agents)
            discover.assert_not_called()

    def test_default_public_run_dispatches_to_multi_source(self):
        expected = {"business": "Owner", "agent_runs": []}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder", "TAVILY_API_KEY": "test-placeholder"}), \
             patch.object(sa, "run_multi_source", return_value=expected) as multi, \
             patch.object(ca, "run_agent", side_effect=AssertionError("legacy single agent selected")):
            result = ca.run("Owner", "bakery", "Seattle", max_workers=2, max_agents=2)
        self.assertEqual(result, expected)
        self.assertEqual(multi.call_count, 1)
        self.assertEqual(multi.call_args.kwargs["max_agents"], 2)


class MergeAndIsolationTests(unittest.TestCase):
    def test_discovery_excludes_owner_and_collapses_duplicate_branch_identities(self):
        def discovery_loop(*args, **kwargs):
            self.assertEqual(kwargs["max_turns"], 6)
            ca.submit_report.call({
                "competitors": [BRANCH, {**BRANCH, "name": "NEARBY BAKERY", "address": "2 MAIN STREET, SEATTLE"},
                                {**BRANCH, "name": "  OWNER  "}],
                "gaps_and_caveats": [],
            })

        with patch.object(ca, "run_agent", side_effect=discovery_loop), patch.object(ca, "GOOGLE_PLACES_API_KEY", None):
            result = sa._run_discovery("Owner", "bakery", "Seattle", OwnerMenu(), max_workers=1)
        self.assertEqual(len(result["report"]["competitors"]), 1)
        self.assertEqual(result["report"]["competitors"][0]["name"], BRANCH["name"])
        self.assertEqual(result["run"]["competitor_count"], 1)
        self.assertEqual(result["report"]["evidence_bundle"], {"menu_observations": [], "review_observations": []})

    def test_conflicting_ratings_hours_and_counts_are_not_averaged(self):
        discovery = facts()
        first = facts(rating=4.8, review_count=900, hours="7am–5pm")
        second = facts(rating=4.2, review_count=300, hours="8am–4pm")
        merged = sa.merge_source_reports(discovery, [
            {"agent_id": "google_reviews", "report": first},
            {"agent_id": "yelp_reviews", "report": second},
        ])
        self.assertEqual(len(merged["competitors"]), 1)
        competitor = merged["competitors"][0]
        self.assertIsNone(competitor["rating"])
        self.assertIsNone(competitor["review_count"])
        self.assertIsNone(competitor["hours"])
        self.assertTrue(merged["gaps_and_caveats"])
        self.assertEqual(first["competitors"][0]["rating"], 4.8, "Source reports must remain unchanged")
        self.assertEqual(second["competitors"][0]["rating"], 4.2)

    def test_identical_cross_source_review_observations_count_once(self):
        review = {
            "business_name": BRANCH["name"], "address": BRANCH["address"],
            "source_url": "https://trusted.example/reviews", "text": "I enjoyed the croissant.",
            "source_kind": "review_text", "published_at": date.today().isoformat(), "review_id": "review-1",
            "mentions": [{"product": "croissant", "sentiment": "positive"}],
        }
        source = facts(reviews=[review])
        merged = sa.merge_source_reports(facts(), [
            {"agent_id": "first_source", "report": source},
            {"agent_id": "second_source", "report": copy.deepcopy(source)},
        ])
        bundle = EvidenceBundle.model_validate(merged["evidence_bundle"])
        self.assertEqual(len(bundle.review_observations), 1)
        result = analyze_market("Owner", "1 Main Street, Seattle", evidence=bundle)
        self.assertEqual(result.evidence_counts["unique_review_observations"], 1)

    def test_merge_rejects_a_source_branch_outside_discovery(self):
        unexpected = facts()
        unexpected["competitors"][0]["address"] = "99 Another Branch, Seattle"
        with self.assertRaises(ValueError):
            sa.merge_source_reports(facts(), [{"agent_id": "wrong_branch", "report": unexpected}])

    def test_each_specialist_and_each_concurrent_run_has_a_separate_ledger_and_client(self):
        barrier = Barrier(4, timeout=5)
        sessions, clients, lock = [], [], Lock()

        class FakeTavily:
            def __init__(self, **kwargs):
                with lock:
                    clients.append(self)

            def search(self, query, **kwargs):
                return {"results": [{"url": f"https://trusted.example/{query}", "content": "Observed information", "title": query}]}

        def agent_loop(*args, **kwargs):
            session = ca._active_session.get()
            with lock:
                sessions.append(session)
            barrier.wait()
            query = TEST_CALL.get()
            ca.search_web.call({"query": query})
            ca.submit_report.call({"competitors": [{**BRANCH, "sources": [f"https://trusted.example/{query}"]}], "gaps_and_caveats": []})

        profile = sa.SourceProfile(id="official_menus", domains=("trusted.example",), instructions="Inspect this source", allow_page_reads=True)
        def run(label):
            token = TEST_CALL.set(label)
            try:
                return sa._run_specialist(profile, label, "bakery", "Seattle", OwnerMenu(), [BRANCH], max_workers=1)
            finally:
                TEST_CALL.reset(token)

        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-placeholder"}), \
             patch.object(ca, "TavilyClient", FakeTavily), patch.object(ca, "run_agent", side_effect=agent_loop), \
             ThreadPoolExecutor(max_workers=4) as pool:
            labels = ["runA_source1", "runA_source2", "runB_source1", "runB_source2"]
            results = list(pool.map(run, labels))
        self.assertEqual(len({id(session) for session in sessions}), 4)
        self.assertEqual(len(clients), 4)
        for label, result in zip(labels, results):
            self.assertEqual(result["run"]["status"], "complete")
            self.assertEqual([item["url"] for item in result["run"]["source_coverage"]["sources"]], [f"https://trusted.example/{label}"])
        self.assertIsNone(ca._active_session.get())


if __name__ == "__main__":
    unittest.main()
