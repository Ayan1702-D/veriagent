"""Unit and integration tests for L5 LangGraph execution, budget exhaustion, and loop limits."""

import ast
from typing import Any, cast

import pytest

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.core.errors import VeriAgentError
from veriagent.graph.builder import build_verification_graph
from veriagent.graph.edges import should_research_or_report
from veriagent.graph.nodes.contradiction import run_contradiction_node
from veriagent.graph.nodes.extractor import run_extractor_node
from veriagent.graph.nodes.planner import run_planner_node
from veriagent.graph.nodes.reporter import run_reporter_node
from veriagent.graph.nodes.researcher import run_researcher_node
from veriagent.graph.state import GraphState
from veriagent.llm.client import LLMOutputValidationError
from veriagent.llm.fake import FakeLLM
from veriagent.schemas import Claim, Evidence, Finding, RunBudget, Source, SubQuestion, Verdict
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


def test_planner_uses_audited_fallback_after_invalid_model_output() -> None:
    """A malformed planner response should still yield a searchable question."""

    class InvalidPlanner(FakeLLM):
        def complete(self, *args: Any, **kwargs: Any) -> Any:
            raise LLMOutputValidationError("invalid planner JSON")

    recorder = AuditRecorder(run_id="run-planner-fallback")
    state: GraphState = {
        "claim": Claim(text="Electric vehicles always have fewer emissions."),
        "subquestions": [],
        "sources": [],
        "snapshots": {},
        "evidence": [],
        "findings": [],
        "report": None,
        "loop_count": 0,
        "max_loops": 1,
        "has_gaps": False,
        "budget": BudgetGovernor(RunBudget()),
        "recorder": recorder,
        "llm": InvalidPlanner(),
        "search_providers": [],
        "fetch_fn": fake_fetcher,
    }

    result = run_planner_node(state)

    assert result["budget_exhausted"] is False
    assert result["subquestions"][0].search_queries == [state["claim"].text]
    assert recorder.events()[0].payload["reason"] == "invalid_llm_output"


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


@pytest.mark.asyncio
@pytest.mark.parametrize("max_loops", [0, 1])
async def test_researcher_fetches_hits_from_final_allowed_search(max_loops: int) -> None:
    """The search cap must not discard results returned by the last search."""

    class FinalSearchProvider(FakeSearchProvider):
        async def search(self, *args: Any, **kwargs: Any) -> list[SearchResult]:
            kwargs["budget"].consume("searches", 1)
            return await super().search(*args, **kwargs)

    claim = Claim(text="Electric vehicles emit less on clean grids.")
    provider = FinalSearchProvider(
        [
            SearchResult(
                title="EV Study",
                url="https://example.org/ev-study",
                snippet="EV evidence",
                provider="fake",
            )
        ]
    )
    state = cast(
        GraphState,
        {
            "subquestions": [
                SubQuestion(
                    claim_id=claim.id,
                    question="What are EV emissions on clean grids?",
                    search_queries=["EV clean grid emissions"],
                )
            ],
            "search_providers": [provider],
            "budget": BudgetGovernor(RunBudget(max_searches=1, max_loops=max_loops)),
            "recorder": AuditRecorder(run_id="run-final-search"),
            "fetch_fn": fake_fetcher,
            "sources": [],
            "snapshots": {},
        },
    )

    result = await run_researcher_node(state)

    assert len(result["sources"]) == 1
    assert len(result["snapshots"]) == 1


@pytest.mark.asyncio
async def test_researcher_reserves_fetches_for_later_queries() -> None:
    """A first query with many hits must leave fetch capacity for the next one."""

    class ManyHitsProvider:
        name = "many_hits"

        def __init__(self, label: str) -> None:
            self.label = label

        async def search(self, query: str, budget: BudgetGovernor, **_: Any) -> list[SearchResult]:
            budget.consume("searches", 1)
            return [
                SearchResult(
                    title=f"{query} result {index}",
                    url=f"https://example.org/{query}/{self.label}/{index}",
                    snippet="test evidence",
                    provider=self.name,
                )
                for index in range(3)
            ]

    attempted: list[str] = []

    async def counted_fetch(url: str, budget: BudgetGovernor, **_: Any) -> FetchedDocument:
        attempted.append(url)
        budget.consume("fetches", 1)
        return await fake_fetcher(url)

    claim = Claim(text="A claim with two research questions.")
    state = cast(
        GraphState,
        {
            "subquestions": [
                SubQuestion(
                    claim_id=claim.id,
                    question="What supports the first part?",
                    search_queries=["first"],
                ),
                SubQuestion(
                    claim_id=claim.id,
                    question="What supports the second part?",
                    search_queries=["second"],
                ),
            ],
            "search_providers": [ManyHitsProvider("a"), ManyHitsProvider("b")],
            "budget": BudgetGovernor(RunBudget(max_searches=4, max_fetches=6)),
            "recorder": None,
            "fetch_fn": counted_fetch,
            "sources": [],
            "snapshots": {},
        },
    )

    await run_researcher_node(state)

    assert len([url for url in attempted if "/first/" in url]) == 3
    assert len([url for url in attempted if "/second/" in url]) == 3


def test_no_evidence_produces_insufficient_report_without_model_call() -> None:
    """An empty retrieval should not call the strong model or invent citations."""
    claim = Claim(text="A minister cited strong GST collections.")
    llm = FakeLLM()
    recorder = AuditRecorder(run_id="run-no-evidence")
    state = cast(
        GraphState,
        {
            "claim": claim,
            "evidence": [],
            "sources": [],
            "budget": BudgetGovernor(RunBudget()),
            "llm": llm,
            "recorder": recorder,
        },
    )

    analysis = run_contradiction_node(state)
    state["findings"] = analysis["findings"]
    report = run_reporter_node(state)["report"]

    assert report.verdict == Verdict.INSUFFICIENT
    assert report.citations == []
    assert llm.calls == []
    assert [event.type for event in recorder.events()] == [
        "analysis_completed",
        "report_completed",
    ]


def test_extractor_uses_stored_pages_after_search_and_fetch_caps() -> None:
    """Resource caps on retrieval must not discard already fetched source text."""
    claim = Claim(text="EVs produce fewer emissions on clean grids.")
    source = Source(
        url="https://example.org/ev-study",
        title="EV Study",
        domain="example.org",
        snapshot_hash="sha256:test",
    )
    quote = "Electric cars produce fewer emissions on clean grids."
    budget = BudgetGovernor(RunBudget(max_searches=1, max_fetches=1))
    budget.consume("searches", 1)
    budget.consume("fetches", 1)
    llm = FakeLLM(
        responses={
            "extractor": {
                "items": [
                    {"quote": quote, "stance": "supports", "context_conditions": ["clean grids"]}
                ]
            }
        }
    )
    state = cast(
        GraphState,
        {
            "claim": claim,
            "sources": [source],
            "snapshots": {source.id: quote},
            "evidence": [],
            "budget": budget,
            "llm": llm,
            "recorder": None,
        },
    )

    extracted = run_extractor_node(state)["evidence"]

    assert len(extracted) == 1
    assert extracted[0].quote_verified is True
    assert len(llm.calls) == 1


def test_extractor_model_outage_yields_audited_incomplete_report() -> None:
    """A failed extractor must not turn fetched text into an invented verdict."""

    class UnavailableLLM(FakeLLM):
        def complete(self, *args: Any, **kwargs: Any) -> Any:
            raise VeriAgentError("provider unavailable")

    claim = Claim(text="Unrest in France has ended completely.")
    source = Source(
        url="https://example.org/france",
        domain="example.org",
        snapshot_hash="sha256:test",
    )
    recorder = AuditRecorder(run_id="run-extractor-outage")
    state = cast(
        GraphState,
        {
            "claim": claim,
            "sources": [source],
            "snapshots": {source.id: "A news story about unrest in France."},
            "evidence": [],
            "budget": BudgetGovernor(RunBudget()),
            "llm": UnavailableLLM(),
            "recorder": recorder,
        },
    )

    state["evidence"] = run_extractor_node(state)["evidence"]
    state["findings"] = run_contradiction_node(state)["findings"]
    report = run_reporter_node(state)["report"]

    assert report.verdict == Verdict.INSUFFICIENT
    assert report.citations == []
    assert any("model calls failed" in item for item in report.limitations)
    assert "llm_unavailable" in [event.type for event in recorder.events()]


def test_unverified_quote_cannot_yield_partial_conditional_verdict() -> None:
    """A budget-limited report needs verified evidence even for CONDITIONAL."""
    claim = Claim(text="The claim is true under certain conditions.")
    source = Source(
        url="https://example.org/study",
        domain="example.org",
        snapshot_hash="sha256:test",
    )
    state = cast(
        GraphState,
        {
            "claim": claim,
            "findings": [Finding(subclaim_id=claim.text, verdict=Verdict.CONDITIONAL)],
            "sources": [source],
            "evidence": [Evidence(source_id=source.id, quote="Unverified", quote_verified=False)],
            "budget": BudgetGovernor(RunBudget()),
            "llm": FakeLLM(),
            "budget_exhausted": True,
            "recorder": None,
        },
    )

    report = run_reporter_node(state)["report"]

    assert report.verdict == Verdict.INSUFFICIENT
    assert report.citations == []


def test_reporter_synthesizes_verified_evidence_after_search_cap() -> None:
    """Using all search slots should not force an insufficient partial report."""
    claim = Claim(text="EVs produce fewer emissions on clean grids.")
    source = Source(
        url="https://example.org/ev-study",
        domain="example.org",
        snapshot_hash="sha256:test",
    )
    evidence = Evidence(
        source_id=source.id, quote="Clean grids reduce EV emissions.", quote_verified=True
    )
    budget = BudgetGovernor(RunBudget(max_searches=1))
    budget.consume("searches", 1)
    llm = FakeLLM(
        responses={
            "reporter": {
                "overall_verdict": "SUPPORTED",
                "limitations": [],
                "cited_source_ids": [source.id],
            }
        }
    )
    state = cast(
        GraphState,
        {
            "claim": claim,
            "findings": [
                Finding(subclaim_id=claim.text, verdict=Verdict.SUPPORTED, supporting=[evidence.id])
            ],
            "sources": [source],
            "evidence": [evidence],
            "budget": budget,
            "llm": llm,
            "recorder": None,
        },
    )

    report = run_reporter_node(state)["report"]

    assert report.verdict == Verdict.SUPPORTED
    assert report.citations == [source]
    assert len(llm.calls) == 1


def _build_test_llm() -> FakeLLM:
    """Construct FakeLLM loaded with canned responses for all nodes."""

    class LinkedFakeLLM(FakeLLM):
        """Link canned findings and entailment to the actual extracted evidence ID."""

        def complete(self, *args: Any, **kwargs: Any) -> Any:
            """Populate evidence links before returning canned node responses."""
            if kwargs["node"] == "contradiction":
                content = kwargs["messages"][1]["content"]
                items = ast.literal_eval(content.split("Evidence: ")[1])
                evidence_id = items[0]["id"]
                self.register(
                    "contradiction",
                    {
                        "subclaim_findings": [
                            {
                                "subclaim": "EVs produce fewer emissions in all scenarios",
                                "contradicting_evidence_ids": [evidence_id],
                                "gaps": ["Unclear cutoff percentage"],
                                "verdict": "CONDITIONAL",
                                "confidence": 0.85,
                            }
                        ]
                    },
                )
                self.register(
                    "verifier",
                    {
                        "evaluations": [
                            {
                                "evidence_id": evidence_id,
                                "label": "contradicts",
                                "reason": "Refutes universal superiority",
                            }
                        ]
                    },
                )
            return super().complete(*args, **kwargs)

    return LinkedFakeLLM(
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
    assert any("limit; report uses partial data" in lim.lower() for lim in report.limitations)


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


@pytest.mark.asyncio
async def test_researcher_reserves_time_for_extraction() -> None:
    """Stop fetching when a search spends the retrieval time allocation."""
    elapsed = [0.0]
    budget = BudgetGovernor(RunBudget(max_seconds=60), clock=lambda: elapsed[0])

    class SlowSearch(FakeSearchProvider):
        async def search(self, *args: Any, **kwargs: Any) -> list[SearchResult]:
            """Simulate a search consuming the research time allocation."""
            elapsed[0] = 31.0
            return await super().search(*args, **kwargs)

    provider = SlowSearch(
        [SearchResult(title="Study", url="https://example.org/study", provider="fake")]
    )
    claim = Claim(text="Test claim")
    state = cast(
        GraphState,
        {
            "subquestions": [
                SubQuestion(
                    claim_id=claim.id, question="Test question", search_queries=["first", "second"]
                )
            ],
            "search_providers": [provider],
            "budget": budget,
            "fetch_fn": fake_fetcher,
            "sources": [],
            "snapshots": {},
        },
    )

    result = await run_researcher_node(state)

    assert provider.called_count == 1
    assert result["sources"] == []
    assert budget.remaining()["seconds"] == 29.0


@pytest.mark.asyncio
async def test_extractor_leaves_time_for_analysis() -> None:
    """Do not start another source when extraction has spent its time allocation."""
    from veriagent.graph.nodes.extractor import ExtractorOutput, RawExtractedEvidence

    elapsed = [0.0]
    budget = BudgetGovernor(RunBudget(max_seconds=60), clock=lambda: elapsed[0])
    calls: list[str] = []

    class SlowExtractor(FakeLLM):
        def complete(self, *args: Any, **kwargs: Any) -> Any:
            """Return one verified quote after spending the extraction allocation."""
            calls.append(kwargs["node"])
            elapsed[0] = 31.0
            return ExtractorOutput(items=[RawExtractedEvidence(quote="A verified quotation.")])

    sources = [
        Source(
            url=f"https://example.org/{index}", domain="example.org", snapshot_hash="sha256:test"
        )
        for index in range(2)
    ]
    state = cast(
        GraphState,
        {
            "claim": Claim(text="A test claim"),
            "sources": sources,
            "snapshots": {source.id: "A verified quotation." for source in sources},
            "llm": SlowExtractor(),
            "budget": budget,
            "evidence": [],
        },
    )

    result = run_extractor_node(state)

    assert calls == ["extractor"]
    assert len(result["evidence"]) == 1
    assert result["evidence"][0].quote_verified
    assert budget.remaining()["seconds"] == 29.0
