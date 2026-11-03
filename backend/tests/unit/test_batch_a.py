"""Regression coverage for finding isolation, loop identity, and partial reports."""

from typing import Any, cast

import pytest

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.core.errors import BudgetExceededError
from veriagent.graph.builder import build_verification_graph
from veriagent.graph.nodes.contradiction import run_contradiction_node
from veriagent.graph.nodes.extractor import run_extractor_node
from veriagent.graph.nodes.planner import run_planner_node
from veriagent.graph.nodes.reporter import run_reporter_node
from veriagent.graph.nodes.researcher import run_researcher_node
from veriagent.graph.nodes.verifier import run_verifier_node
from veriagent.graph.state import GraphState
from veriagent.llm.client import load_prompt
from veriagent.llm.fake import FakeLLM
from veriagent.schemas import (
    Claim,
    Evidence,
    Finding,
    RunBudget,
    Source,
    Stance,
    SubQuestion,
    Verdict,
)
from veriagent.tools.search.base import SearchResult


def state_with_evidence() -> GraphState:
    """Build an isolated state with one linked, verified quote."""
    source = Source(
        id="source",
        url="https://example.org/study",
        domain="example.org",
        snapshot_hash="sha256:test",
    )
    evidence = Evidence(
        id="evidence",
        source_id=source.id,
        quote="A verified quotation.",
        quote_verified=True,
        stance=Stance.NEUTRAL,
    )
    return {
        "claim": Claim(text="A test claim"),
        "sources": [source],
        "snapshots": {source.id: evidence.quote},
        "evidence": [evidence],
        "findings": [
            Finding(
                subclaim_id="A test claim",
                supporting=[evidence.id],
                verdict=Verdict.SUPPORTED,
                confidence=0.8,
            )
        ],
        "subquestions": [],
        "report": None,
        "has_gaps": False,
        "loop_count": 0,
        "max_loops": 1,
        "budget": BudgetGovernor(RunBudget()),
        "recorder": AuditRecorder("batch-a"),
        "llm": FakeLLM(),
        "search_providers": [],
        "fetch_fn": None,
    }


def test_reporter_cannot_promote_incomplete_findings_or_cite_unlinked_sources() -> None:
    """An optimistic model cannot override insufficient findings or add unrelated citations."""
    state = state_with_evidence()
    unrelated = Source(
        id="unrelated",
        url="https://example.org/other",
        domain="example.org",
        snapshot_hash="sha256:other",
    )
    state["sources"].append(unrelated)
    state["evidence"].append(
        Evidence(source_id=unrelated.id, quote="Other quote", quote_verified=True)
    )
    state["findings"].append(Finding(subclaim_id="Unresolved claim"))
    state["llm"] = FakeLLM(
        {
            "reporter": {
                "overall_verdict": "SUPPORTED",
                "cited_source_ids": [unrelated.id, "invented"],
            }
        }
    )
    report = run_reporter_node(state)["report"]
    assert report.verdict == Verdict.INSUFFICIENT
    assert [source.id for source in report.citations] == ["source"]


def test_reporter_does_not_fall_back_to_unlinked_verified_sources() -> None:
    """Verified quotes outside the findings never become fallback citations."""
    state = state_with_evidence()
    state["findings"][0] = Finding(subclaim_id="A test claim", verdict=Verdict.SUPPORTED)
    report = run_reporter_node(state)["report"]
    assert report.verdict == Verdict.INSUFFICIENT
    assert report.citations == []


@pytest.mark.parametrize("node", ["contradiction", "verifier", "reporter"])
def test_node_budget_exception_produces_partial_report(node: str) -> None:
    """Budget exceptions at each post-extraction node produce an explicit partial report."""

    class ExhaustedLLM(FakeLLM):
        def complete(self, *args: Any, **kwargs: Any) -> Any:
            """Simulate a cap reached inside the requested model call."""
            raise BudgetExceededError("tokens", 101, 100)

    state = state_with_evidence()
    state["llm"] = ExhaustedLLM()
    if node == "contradiction":
        state.update(run_contradiction_node(state))
    elif node == "verifier":
        state.update(run_verifier_node(state))
    report = run_reporter_node(state)["report"]
    assert any("partial data" in item for item in report.limitations)


def test_extractor_preserves_ids_and_distinct_source_quotes_across_loops() -> None:
    """Repeat extraction skips completed sources and preserves independent quote identities."""
    state = state_with_evidence()
    state["evidence"] = []
    second = state["sources"][0].model_copy(update={"id": "second"})
    state["sources"].append(second)
    state["snapshots"][second.id] = "A verified quotation."
    llm = FakeLLM(
        {
            "extractor": {
                "items": [
                    {"quote": "A verified quotation."},
                    {"quote": "A verified quotation."},
                ]
            }
        }
    )
    state["llm"] = llm
    state.update(run_extractor_node(state))
    first_ids = [e.id for e in state["evidence"]]
    state.update(run_extractor_node(state))
    assert len(first_ids) == len(set(first_ids)) == 2
    assert [e.id for e in state["evidence"]] == first_ids
    assert len(llm.calls) == 2
    assert all(call["messages"][0]["content"] == load_prompt("extractor") for call in llm.calls)


def test_extractor_skips_successful_empty_extractions_on_later_loops() -> None:
    """An empty successful extraction is still completed work."""
    state = state_with_evidence()
    state["evidence"] = []
    llm = FakeLLM({"extractor": {"items": []}})
    state["llm"] = llm
    state.update(run_extractor_node(state))
    state.update(run_extractor_node(state))
    assert len(llm.calls) == 1


def test_verifier_isolates_stance_by_finding_and_accounts_for_loops() -> None:
    """The same quote can support one finding and contradict another without global mutation."""
    state = state_with_evidence()
    state["findings"] = [
        Finding(subclaim_id="First claim", supporting=["evidence"], verdict=Verdict.SUPPORTED),
        Finding(subclaim_id="Second claim", contradicting=["evidence"], verdict=Verdict.REFUTED),
    ]
    llm = FakeLLM(
        {
            "verifier": [
                {
                    "evaluations": [
                        {"evidence_id": "evidence", "label": "supports", "reason": "First"}
                    ]
                },
                {"queries": []},
                {
                    "evaluations": [
                        {"evidence_id": "evidence", "label": "contradicts", "reason": "Second"}
                    ]
                },
            ]
        }
    )
    state["llm"] = llm
    result = run_verifier_node(state)
    assert [f.verdict for f in result["findings"]] == [Verdict.SUPPORTED, Verdict.REFUTED]
    assert result["findings"][0].supporting == ["evidence"]
    assert result["findings"][1].contradicting == ["evidence"]
    assert result["evidence"][0].stance == Stance.NEUTRAL
    assert state["budget"].usage()["loops"] == 1
    assert all(
        call["messages"][0]["content"].startswith(load_prompt("verifier")) for call in llm.calls
    )


def test_planner_qualifiers_use_word_boundaries() -> None:
    """Embedded fragments such as 'all' in 'small' are not scope qualifiers."""
    state = state_with_evidence()
    state["claim"] = Claim(text="Small balloons only rise; ALWAYS check them.")
    llm = FakeLLM({"planner": {}})
    state["llm"] = llm
    result = run_planner_node(state)
    assert result["claim"].qualifiers == ["always", "only"]
    assert llm.calls[0]["messages"][0]["content"] == load_prompt("planner")


@pytest.mark.asyncio
async def test_researcher_round_robins_one_provider_per_query() -> None:
    """Multiple providers cannot multiply the search cost of a query."""
    calls: list[tuple[str, str]] = []

    class CountingProvider:
        """Account for every provider invocation."""

        def __init__(self, name: str) -> None:
            """Set provider identity."""
            self.name = name

        async def search(
            self,
            query: str,
            limit: int = 5,
            budget: BudgetGovernor | None = None,
            recorder: AuditRecorder | None = None,
        ) -> list[SearchResult]:
            """Return no hits while charging one search."""
            assert budget is not None
            budget.consume("searches")
            calls.append((self.name, query))
            return []

    state = state_with_evidence()
    state["subquestions"] = [
        SubQuestion(
            claim_id=state["claim"].id,
            question="Test question",
            search_queries=["first", "second", "third"],
        )
    ]
    state["search_providers"] = [CountingProvider("one"), CountingProvider("two")]
    state["budget"] = BudgetGovernor(RunBudget(max_searches=2))
    await run_researcher_node(state)
    assert calls == [("one", "first"), ("two", "second")]
    assert state["budget"].usage()["searches"] == 2


@pytest.mark.asyncio
async def test_graph_exhaustion_after_extractor_preserves_partial_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The compiled graph still reports when tokens run out immediately after extraction."""
    state = state_with_evidence()
    state["budget"] = BudgetGovernor(RunBudget(max_llm_tokens=20))
    state["llm"] = FakeLLM({"planner": {}, "contradiction": {}}, tokens_per_call=10)

    def exhausted_extractor(current: GraphState) -> dict[str, Any]:
        """Consume the final tokens while retaining extracted evidence."""
        current["budget"].consume("tokens", 10)
        return {"evidence": current["evidence"]}

    monkeypatch.setattr("veriagent.graph.builder.run_extractor_node", exhausted_extractor)
    final = await build_verification_graph().ainvoke(cast(GraphState, state))
    report = final["report"]
    assert report is not None
    assert report.verdict == Verdict.INSUFFICIENT
    assert final["evidence"][0].quote_verified
    assert any("partial data" in item for item in report.limitations)
