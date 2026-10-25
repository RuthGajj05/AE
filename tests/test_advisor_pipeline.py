"""Mocked orchestration: bounded parallelism, isolated provenance and advice inputs."""

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import advisor, agent_loop, business_agent, competitor_agent
from agent.market_intelligence import OwnerMenu


ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today()
CALL_CONTEXT = ContextVar("test_tool_context", default=None)


class Tool:
    def __init__(self, name, function):
        self.name, self.function = name, function

    def call(self, values):
        return self.function(values)

    def to_dict(self):
        return {"name": self.name, "input_schema": {"type": "object", "properties": {}}}


def tool_call(name, call_id, values=None):
    return SimpleNamespace(type="tool_use", name=name, id=call_id, input=values or {})


def client_with_turns(turns):
    client = Mock()
    client.beta.messages.create.side_effect = [SimpleNamespace(content=calls, stop_reason="tool_use") for calls in turns]
    return client


def facts(reviews=None):
    return {
        "business": "Owner Bakery", "type": "bakery", "location": "1 Main Street, Seattle",
        "date": TODAY.isoformat(), "mode": "live_research", "competitors": [],
        "gaps_and_caveats": [], "source_coverage": {"sources": [], "failed_extractions": []},
        "evidence_bundle": {
            "menu_observations": [{
                "business_name": "Nearby Bakery", "address": "2 Main Street, Seattle",
                "source_url": "https://example.com/menu", "product": product,
                "observed_at": TODAY.isoformat(),
            } for product in ("Chocolate croissant", "Matcha latte")] + [{
                # A second shop sells matcha under another name (grouped by category,
                # since the advisor needs 2+ competitors per gap) plus a one-off specialty.
                "business_name": "Corner Cafe", "address": "9 Main Street, Seattle",
                "source_url": "https://example.org/menu", "product": product, "category": category,
                "observed_at": TODAY.isoformat(),
            } for product, category in (("Iced Ceremonial Matcha", "matcha latte"), ("Pain au Chocolat", "chocolate croissant"), ("Ube Mochi Donut", "ube mochi donut"))],
            "review_observations": reviews or [],
        },
    }


def reviews(period, positive):
    return [{
        "business_name": "Nearby Bakery", "address": "2 Main Street, Seattle",
        "source_url": "https://example.com/reviews", "text": f"{period} review number {index}",
        "published_at": (TODAY - timedelta(days=40 if period == "previous" else 10)).isoformat(),
        "source_kind": "review_text", "review_id": f"{period}-{index}",
        "mentions": [{"product": "Matcha latte", "sentiment": "positive"}] if index < positive else [],
    } for index in range(10)]


def advice_client():
    client = Mock()
    client.beta.messages.parse.return_value = SimpleNamespace(
        stop_reason="end_turn", parsed_output=advisor.AdvisorReport(
            snapshot="Check the measured opportunities before a limited trial.",
            strengths=[], gaps_vs_competitors=[], recommendations=[], caveats=[],
        ),
    )
    return client


class SharedAgentLoopTests(unittest.TestCase):
    def test_retrievals_are_parallel_with_context_and_finish_before_submission(self):
        barrier = Barrier(2)
        shared = {"retrieved": []}
        token = CALL_CONTEXT.set(shared)
        try:
            def retrieve(values):
                self.assertIs(CALL_CONTEXT.get(), shared)
                barrier.wait(timeout=3)
                CALL_CONTEXT.get()["retrieved"].append(values["name"])
                return values["name"]

            def submit(values):
                self.assertIs(CALL_CONTEXT.get(), shared)
                self.assertEqual(set(shared["retrieved"]), {"a", "b"})
                return "validated"

            retrieve_tool, submit_tool = Tool("retrieve", retrieve), Tool("submit", submit)
            calls = [tool_call("submit", "submit-id", {"accepted": True}),
                     tool_call("retrieve", "a-id", {"name": "a"}), tool_call("retrieve", "b-id", {"name": "b"})]
            client = client_with_turns([calls])
            with patch.object(agent_loop.anthropic, "Anthropic", return_value=client):
                result = agent_loop.run_agent("system", "prompt", [retrieve_tool, submit_tool], submit_tool, "test", max_workers=2)
            self.assertEqual(result, {"accepted": True})
            returned = client.beta.messages.create.call_args.kwargs["messages"][-1]["content"]
            self.assertEqual([value["tool_use_id"] for value in returned], ["submit-id", "a-id", "b-id"])
        finally:
            CALL_CONTEXT.reset(token)

    def test_failed_submission_can_retry_and_duplicate_success_does_not_overwrite(self):
        submitted = []

        def submit(values):
            if not values.get("valid"):
                raise ValueError("missing source")
            submitted.append(values["value"])
            return "validated"

        submit_tool = Tool("submit", submit)
        client = client_with_turns([
            [tool_call("submit", "bad", {})],
            [tool_call("submit", "good", {"valid": True, "value": "first"}),
             tool_call("submit", "duplicate", {"valid": True, "value": "second"})],
        ])
        with patch.object(agent_loop.anthropic, "Anthropic", return_value=client):
            result = agent_loop.run_agent("system", "prompt", [submit_tool], submit_tool, "test")
        self.assertEqual(result["value"], "first")
        self.assertEqual(submitted, ["first"])
        messages = client.beta.messages.create.call_args.kwargs["messages"]
        self.assertTrue(messages[2]["content"][0]["is_error"])
        self.assertTrue(messages[-1]["content"][1]["is_error"])

    def test_concurrent_runs_do_not_share_tool_context(self):
        barrier = Barrier(2)

        def retrieve(_):
            barrier.wait(timeout=3)
            CALL_CONTEXT.get()["seen"].append(CALL_CONTEXT.get()["name"])
            return "retrieved"

        retrieve_tool = Tool("retrieve", retrieve)
        submit_tool = Tool("submit", lambda _: "submitted")
        def run(name):
            context = {"name": name, "seen": []}
            token = CALL_CONTEXT.set(context)
            try:
                agent_loop.run_agent("system", name, [retrieve_tool, submit_tool], submit_tool, name, max_workers=1)
                return context["seen"]
            finally:
                CALL_CONTEXT.reset(token)

        factory = lambda: client_with_turns([[tool_call("retrieve", "retrieve"), tool_call("submit", "submit")]])
        with patch.object(agent_loop.anthropic, "Anthropic", side_effect=factory), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ("owner", "competitor")))
        self.assertEqual(results, [["owner"], ["competitor"]])

    def test_invalid_worker_count_fails_before_constructing_api_client(self):
        submit_tool = Tool("submit", lambda _: "ok")
        with patch.object(agent_loop.anthropic, "Anthropic") as constructor:
            for invalid in (0, 11, 1.5, True):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    agent_loop.run_agent("system", "prompt", [submit_tool], submit_tool, "test", max_workers=invalid)
            constructor.assert_not_called()


class BusinessPresenceTests(unittest.TestCase):
    def test_presence_has_its_own_session_and_restores_surrounding_competitor_session(self):
        owner_url, competitor_url = "https://example.com/owner", "https://example.com/competitor"
        def presence_loop(*args, **kwargs):
            self.assertEqual(kwargs["max_workers"], 2)
            competitor_agent._source_ledger().add(owner_url, "Owner menu", "page_text")
            return {"found_online": True, "sources": [owner_url]}

        with competitor_agent.research_session() as outer:
            outer.ledger.add(competitor_url, "Competitor menu", "page_text")
            with patch.object(business_agent, "run_agent", side_effect=presence_loop):
                result = business_agent.research_presence("Owner Bakery", "Seattle", max_workers=2)
            self.assertIs(competitor_agent._source_ledger(), outer.ledger)
            self.assertEqual(set(outer.ledger.records), {competitor_url})
        self.assertEqual([source["url"] for source in result["source_coverage"]["sources"]], [owner_url])

    def test_known_sales_fixture_is_labeled_synthetic_and_partial(self):
        csv = "Date,Time,Item,Qty,Gross Sales\n2026-10-25,08:00:00,Croissant,2,$10.00\n"
        with patch.object(Path, "open", return_value=io.StringIO(csv)):
            result = business_agent.analyze_sales(ROOT / "data/sample_sales.csv")
        self.assertTrue(result["is_synthetic"])
        self.assertEqual(result["data_origin"], "synthetic_demo")
        self.assertTrue(any("not a complete current menu" in value for value in result["caveats"]))


class PosIntegrationTests(unittest.TestCase):
    ROWS = [
        {"Date": "2026-10-25", "Time": "08:00:00", "Item": "Pain au Chocolat", "Qty": 0.5, "Gross Sales": 2.5},
        {"Date": "2026-10-25", "Time": "09:00:00", "Item": "Pain au Chocolat", "Qty": "1.25", "Gross Sales": "$6.25"},
    ]

    def test_numeric_money_and_fractional_pos_quantities_are_preserved(self):
        result = business_agent.analyze_rows(self.ROWS, source="square", environment="production")
        self.assertEqual(result["items"][0]["units"], 1.75)
        self.assertEqual(result["items"][0]["avg_price"], 5.0)
        self.assertEqual(result["total_revenue"], 8.75)
        self.assertEqual(result["sales_source"], "square")
        self.assertEqual(result["sales_environment"], "production")
        self.assertEqual(result["data_origin"], "pos_api")
        self.assertFalse(result["is_synthetic"])

    def test_square_sandbox_dispatch_records_source_and_marks_synthetic(self):
        with patch.object(advisor.pos, "fetch_square", return_value=self.ROWS) as fetch, \
             patch.dict(os.environ, {"SQUARE_ENVIRONMENT": "sandbox"}):
            result = advisor.load_sales("square", 14)
        fetch.assert_called_once_with(14)
        self.assertTrue(result["is_synthetic"])
        self.assertEqual(result["data_origin"], "synthetic_demo")
        self.assertEqual(result["sales_environment"], "sandbox")
        self.assertEqual(result["sales_source"], "square")

    def test_toast_dispatch_and_explicit_demo_label(self):
        with patch.object(advisor.pos, "fetch_toast", return_value=self.ROWS) as fetch:
            production = advisor.load_sales("toast", 7)
            demo = advisor.load_sales("toast", 7, synthetic=True)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(production["sales_source"], "toast")
        self.assertFalse(production["is_synthetic"])
        self.assertTrue(demo["is_synthetic"])

    def test_csv_dispatch_preserves_explicit_synthetic_flag(self):
        with patch.object(business_agent, "analyze_sales", return_value={"is_synthetic": True}) as csv, \
             patch.object(advisor.pos, "fetch_square") as square, patch.object(advisor.pos, "fetch_toast") as toast:
            result = advisor.load_sales("uploaded.csv", 56, synthetic=True)
        csv.assert_called_once_with("uploaded.csv", synthetic=True)
        square.assert_not_called()
        toast.assert_not_called()
        self.assertTrue(result["is_synthetic"])

    def test_square_sales_flow_through_advisor_without_losing_demo_or_menu_safety(self):
        with tempfile.TemporaryDirectory() as directory, \
            patch.object(advisor.fast_competitors, "run", return_value=facts()), \
            patch.object(business_agent, "research_presence", return_value={}), \
            patch.object(advisor.pos, "fetch_square", return_value=self.ROWS) as fetch, \
            patch.dict(os.environ, {"SQUARE_ENVIRONMENT": "sandbox"}), \
            patch.object(advisor.anthropic, "Anthropic", return_value=advice_client()):
            result = advisor.run("Owner Bakery", "bakery", "1 Main Street, Seattle", sales_source="square", days=14, reports_dir=directory)
        fetch.assert_called_once_with(14)
        self.assertEqual(result["mode"], "demo")
        self.assertFalse(result["owner_menu"]["confirmed_complete"])
        self.assertEqual(result["owner_menu"]["products"], ["Pain au Chocolat"])
        self.assertEqual([gap["product"] for gap in result["market_intelligence"]["product_gaps"]], ["matcha latte"])

    def test_invalid_pos_day_range_fails_before_any_research(self):
        with patch.object(advisor.fast_competitors, "run") as competitor_run, patch.object(advisor.pos, "fetch_square") as fetch:
            for days in (0, -1, True, 2.5):
                with self.subTest(days=days), self.assertRaises(ValueError):
                    advisor.run("Owner", "bakery", "Seattle", "square", days=days)
            competitor_run.assert_not_called()
            fetch.assert_not_called()


class AdvisorPipelineTests(unittest.TestCase):
    def test_sales_first_then_research_stages_in_parallel_then_intelligence_precedes_advice(self):
        # Sales run first so competitor agents can price the owner's top sellers;
        # competitor and presence research then run at the same time.
        barrier = Barrier(2)
        completed, lock = set(), Lock()
        sales = {"items": [{"item": "Pain au Chocolat", "units": 12}], "is_synthetic": False}
        def stage(name, value):
            def research(*args, **kwargs):
                if name == "sales":
                    self.assertEqual(completed, set())
                else:
                    self.assertIn("sales", completed)
                    barrier.wait(timeout=3)
                if name == "presence":
                    self.assertEqual(kwargs["max_workers"], 2)
                if name == "competitors":
                    self.assertEqual(args[3], ["Pain au Chocolat"])
                with lock:
                    completed.add(name)
                return copy.deepcopy(value)
            return research

        original_analyze = competitor_agent.analyze_report
        def analyze(report, menu, **kwargs):
            self.assertEqual(completed, {"sales", "presence", "competitors"})
            self.assertFalse(menu.confirmed_complete)
            self.assertIsNone(menu.confirmed_at)
            self.assertEqual(menu.products, ["Pain au Chocolat"])
            return original_analyze(report, menu, **kwargs)

        client = advice_client()
        def parse(**kwargs):
            prompt = kwargs["messages"][0]["content"]
            self.assertIn('"market_intelligence"', prompt)
            self.assertIn('"needs_confirmation"', prompt)
            self.assertIn("insufficient_evidence", prompt)
            return client.beta.messages.parse.return_value
        client.beta.messages.parse.side_effect = parse
        with tempfile.TemporaryDirectory() as directory, \
            patch.object(advisor.fast_competitors, "run", side_effect=stage("competitors", facts())), \
            patch.object(business_agent, "research_presence", side_effect=stage("presence", {"found_online": True})), \
            patch.object(business_agent, "analyze_sales", side_effect=stage("sales", sales)), \
            patch.object(competitor_agent, "analyze_report", side_effect=analyze), \
            patch.object(advisor.anthropic, "Anthropic", return_value=client):
            result = advisor.run("Owner Bakery", "bakery", "1 Main Street, Seattle", "unused.csv", max_workers=2, reports_dir=directory)
            snapshot = json.loads((Path(directory) / result["competitor_snapshot"]).read_text())
        self.assertEqual(result["mode"], "advisor")
        # Matcha is sold by two shops; the ube donut by only one, so it is not a gap.
        self.assertEqual([gap["product"] for gap in result["market_intelligence"]["product_gaps"]], ["matcha latte"])
        self.assertEqual(result["market_intelligence"]["product_gaps"][0]["competitor_count"], 2)
        self.assertEqual(snapshot["mode"], "live_research")
        self.assertNotIn("your_sales", snapshot)
        self.assertEqual(result["market_intelligence"], result["competitors"]["market_intelligence"])

    def test_explicit_menu_is_preserved_and_synthetic_advice_is_always_labeled(self):
        menu = OwnerMenu(products=["Matcha latte"], confirmed_complete=True, confirmed_at=TODAY)
        sales = {"items": [{"item": "Coffee", "units": 12}], "is_synthetic": True, "data_origin": "synthetic_demo"}
        with tempfile.TemporaryDirectory() as directory, \
            patch.object(advisor.fast_competitors, "run", return_value=facts()), \
            patch.object(business_agent, "research_presence", return_value={}), \
            patch.object(business_agent, "analyze_sales", return_value=sales) as sales_mock, \
            patch.object(advisor.anthropic, "Anthropic", return_value=advice_client()):
            result = advisor.run("Owner Bakery", "bakery", "1 Main Street, Seattle", "fake.csv", owner_menu=menu, synthetic_sales=True, reports_dir=directory, use_history=False)
            snapshot = json.loads((Path(directory) / result["competitor_snapshot"]).read_text())
        self.assertEqual(result["owner_menu"], menu.model_dump(mode="json"))
        self.assertEqual(result["mode"], "demo")
        self.assertIn("synthetic sales", result["advice"]["snapshot"])
        self.assertTrue(any("synthetic" in caveat for caveat in result["advice"]["caveats"]))
        self.assertEqual(snapshot["mode"], "live_research")
        self.assertEqual(result["market_intelligence"]["product_gaps"][0]["owner_menu_status"], "confirmed_absent")
        sales_mock.assert_called_once_with("fake.csv", synthetic=True)

    def test_second_advisor_run_uses_saved_competitor_history_for_trends(self):
        with tempfile.TemporaryDirectory() as directory, \
            patch.object(advisor.fast_competitors, "run", side_effect=[facts(reviews("previous", 3)), facts(reviews("current", 6))]), \
            patch.object(business_agent, "research_presence", return_value={}), \
            patch.object(business_agent, "analyze_sales", return_value={"items": [], "is_synthetic": False}), \
            patch.object(advisor.anthropic, "Anthropic", return_value=advice_client()):
            first = advisor.run("Owner Bakery", "bakery", "1 Main Street, Seattle", "unused.csv", reports_dir=directory)
            second = advisor.run("Owner Bakery", "bakery", "1 Main Street, Seattle", "unused.csv", reports_dir=directory)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 2)
        self.assertEqual(first["competitors"]["history_reports_used"], 0)
        self.assertEqual(second["competitors"]["history_reports_used"], 1)
        trend = next(item for item in second["market_intelligence"]["product_trends"] if item["product"] == "matcha latte")
        self.assertEqual(trend["status"], "rising")
        self.assertEqual(trend["change_percentage_points"], 30)
        self.assertEqual((trend["previous"]["total_reviews"], trend["current"]["total_reviews"]), (10, 10))

    def test_invalid_owner_menu_fails_before_research(self):
        with patch.object(advisor.fast_competitors, "run") as competitor_run:
            with self.assertRaises(ValueError):
                advisor.run("Owner Bakery", "bakery", "Seattle", "unused.csv", owner_menu={"products": [""]})
            competitor_run.assert_not_called()


class EntryPointTests(unittest.TestCase):
    def test_package_and_direct_help_require_no_network_or_credentials(self):
        bootstrap = """
import runpy, socket, sys
import anthropic, tavily
def forbidden(*args, **kwargs): raise AssertionError('API/network attempted during --help')
class ForbiddenClient:
    def __init__(self, *args, **kwargs): forbidden()
anthropic.Anthropic = ForbiddenClient
tavily.TavilyClient = ForbiddenClient
socket.socket.connect = forbidden
entry, style = sys.argv[1:]
sys.argv = [entry, '--help']
if style == 'module': runpy.run_module(entry, run_name='__main__')
else:
    sys.path.insert(0, 'agent')
    runpy.run_path(entry, run_name='__main__')
"""
        env = {key: value for key, value in os.environ.items() if key not in {"ANTHROPIC_API_KEY", "TAVILY_API_KEY", "GOOGLE_PLACES_API_KEY"}}
        env["PYTHON_DOTENV_DISABLED"] = "1"
        for entry, style in (("agent.advisor", "module"), ("agent/advisor.py", "script"),
                             ("agent.business_agent", "module"), ("agent/business_agent.py", "script")):
            with self.subTest(entry=entry):
                result = subprocess.run([sys.executable, "-c", bootstrap, entry, style], cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--max-workers", result.stdout)


if __name__ == "__main__":
    unittest.main()
