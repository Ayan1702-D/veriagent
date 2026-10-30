"""Unit and integration tests for L5 LangGraph execution, budget exhaustion, and loop limits."""

from typing import Any

import pytest

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor, RunBudget
from veriagent.graph.builder import build_verification_graph
from veriagent.graph.edges import should_research_or_report
from veriagent.graph.state import GraphState
from veriagent.llm.fake import FakeLLM
from veriagent.schemas import Claim, Verdict
from veriagent.tools.fetch import FetchedDocument
from veriagent.tools.search.base import SearchResult


class FakeSearchProvider:
    """Fake search provider returning canned hits."""

    name: str = "fake_search"

    def __init__(self, hits: list[SearchResult]) -> None:
        self.hits = hits
        self.called_count = 0

    async def search(self, *args: Any, **kwargs: Any) -> list[SearchResult]:
        self.called_count += 1
        return self.hits


async def fake_fetcher(url: str, *args: Any, **kwargs: Any) -> FetchedDocument:
    """Fake HTTP fetch returning realistic snapshot text."""
    html = """
    <html><body>
    <h1>Electric Vehicles and Grid Realities</h1>
    <p>In coal-dominated grids, electric cars produce emissions roughly equal to hybrids.</p>
    <p>However on renewable grids, emissions are cut by 70 percent immediately.</p>
    </body></html>
    """
    return FetchedDocument(url=url, content=html, status_code=200, content_type="text/html")


def _build_test_llm() -> FakeLLM:
    """Construct FakeLLM loaded with canned responses for all nodes."""
    return FakeLLM(
        responses={
            "planner": {
                "qualifiers": ["always", "regardless"],
                "atomic_subclaims": ["EVs produce fewer emissions in all scenarios"],
                "subquestions": ["How do EV lifecycle emissions behave on dirty grids?"],
                "search_queries": [["EV lifecycle emissions coal power"]],
            },
            "extractor": {
                "items": [
                    {
                        "quote": (
                            "In coal-dominated grids, electric cars produce emissions "
                            "roughlyequal to hybrids."
                        ),
                        "date": "2024-05",
                        "stance": "contradicts",
                        "context_conditions": ["coal-dominated grids"],
                    }
                ]
            },
            "contradiction": {
                "subclaim_findings": [
                    {
                        "subclaim": "EVs produce fewer emissions in all scenarios",
                        "supporting_evidence_ids": [],
                        "contradicting_evidence_ids": ["ev-1"],
                        "gaps": ["Unclear cutoff percentage for coal grid parity"],
                        "verdict": "CONDITIONAL",
                        "confidence": 0.85,
                    }
                ]
            },
            "verifier": {
                "evaluations": [
                    {
                        "evidence_id": "ev-1",
                        "label": "contradicts",
                        "reason": "Directly refutes the claim of universal superiority.",
                    }
                ],
            },
            "reporter": {
                "overall_verdict": "CONDITIONAL",
                "limitations": ["Limited data on heavy industrial transport."],
                "cited_source_ids": ["https://example.org/ev-study"],
            },
        },
        tokens_per_call=20,
    )


@pytest.mark.asyncio
async def test_full_graph_run_success() -> None:
    """Verify entire LangGraph compiles and completes an end-to-end fact-checking pipeline."""
    app = build_verification_graph()
    fake_llm = _build_test_llm()
    provider = FakeSearchProvider(
        hits=[
            SearchResult(
                title="EV Study",
                url="https://example.org/ev-study",
                snippet="EV emissions study",
                provider="fake",
            )
        ]
    )

    budget = BudgetGovernor(
        RunBudget(max_llm_tokens=10000, max_searches=10, max_fetches=10, max_loops=1)
    )
    recorder = AuditRecorder(run_id="run-full-1")

    initial_state: GraphState = {
        "claim": Claim(
            text=(
                "Electric vehicles always produce fewer lifetime emissions, regardless of grid mix."
            )
        ),
        "subquestions": [],
        "sources": [],
        "snapshots": {},
        "evidence": [],
        "findings": [],
        "report": None,
        "loop_count": 0,
        "max_loops": 1,
        "has_gaps": False,
        "budget": budget,
        "recorder": recorder,
        "llm": fake_llm,
        "search_providers": [provider],
        "fetch_fn": fake_fetcher,
    }

    final_state = await app.ainvoke(initial_state)

    report = final_state["report"]
    assert report is not None
    assert report.verdict == Verdict.CONDITIONAL
    assert len(report.findings) == 1
    assert len(report.citations) >= 1
    assert report.citations[0].url == "https://example.org/ev-study"

    # Verify audit event sequencing
    events = recorder.events()
    nodes_executed = [e.node for e in events]
    assert "planner" in nodes_executed
    assert "researcher" in nodes_executed
    assert "extractor" in nodes_executed
    assert "verifier" in nodes_executed
    assert "reporter" in nodes_executed


@pytest.mark.asyncio
async def test_graph_budget_exhaustion_generates_partial_report() -> None:
    """Verify graph handles hard budget exhaustion gracefully and emits partial report."""
    fake_llm = _build_test_llm()
    budget = BudgetGovernor(RunBudget(max_llm_tokens=30, max_searches=1, max_fetches=1))
    # Pre-exhaust the budget
    budget.consume("tokens", 25)

    app = build_verification_graph()
    initial_state: GraphState = {
        "claim": Claim(text="EVs are always cleaner."),
        "subquestions": [],
        "sources": [],
        "snapshots": {},
        "evidence": [],
        "findings": [],
        "report": None,
        "loop_count": 0,
        "max_loops": 0,
        "has_gaps": False,
        "budget": budget,
        "recorder": None,
        "llm": fake_llm,
        "search_providers": [FakeSearchProvider([])],
        "fetch_fn": fake_fetcher,
    }

    final_state = await app.ainvoke(initial_state)
    report = final_state["report"]
    assert report is not None
    assert any("budget reached hard limits" in lim.lower() for lim in report.limitations)


def test_edge_routing_loop_limits() -> None:
    """Verify routing respects gaps, loop limits, and budget availability."""
    budget = BudgetGovernor(RunBudget(max_loops=2))

    # Condition 1: Gaps exist and loop_count < max_loops -> loop to researcher
    state1: GraphState = {
        "has_gaps": True,
        "loop_count": 0,
        "max_loops": 2,
        "budget": budget,
    }  # type: ignore[typeddict-item]
    assert should_research_or_report(state1) == "researcher"

    # Condition 2: Max loops reached -> go to reporter
    state2: GraphState = {
        "has_gaps": True,
        "loop_count": 2,
        "max_loops": 2,
        "budget": budget,
    }  # type: ignore[typeddict-item]
    assert should_research_or_report(state2) == "reporter"

    # Condition 3: No gaps -> go to reporter
    state3: GraphState = {
        "has_gaps": False,
        "loop_count": 0,
        "max_loops": 2,
        "budget": budget,
    }  # type: ignore[typeddict-item]
    assert should_research_or_report(state3) == "reporter"
