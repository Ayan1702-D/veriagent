"""Unit tests for L1 schemas, budget governor, audit recorder, and JSON logging."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from veriagent.audit.recorder import AuditRecorder
from veriagent.config import Settings
from veriagent.core.budget import BudgetGovernor
from veriagent.core.errors import BudgetExceededError
from veriagent.core.logging import JsonLogFormatter, reset_run_id, set_run_id
from veriagent.schemas import (
    AuditEvent,
    Claim,
    Evidence,
    Finding,
    Report,
    RunBudget,
    Source,
    SourceType,
    Stance,
    SubQuestion,
    Verdict,
)


class FakeClock:
    """Controllable monotonic clock for testing elapsed seconds."""

    def __init__(self, initial: float = 100.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ListSink:
    """In-memory AuditSink implementation for testing."""

    def __init__(self) -> None:
        self.received: list[AuditEvent] = []

    def emit(self, event: AuditEvent) -> None:
        self.received.append(event)


def test_schemas_and_enums_roundtrip() -> None:
    """Verify core Pydantic models and enums validate and serialize cleanly."""
    claim = Claim(
        text="EVs always emit less CO2 than ICE vehicles regardless of grid.",
        qualifiers=["always", "regardless"],
        atomic_subclaims=["EV lifecycle emissions are lower on coal-heavy grids"],
    )
    sq = SubQuestion(
        claim_id=claim.id,
        question="How do EV emissions compare on coal-heavy grids?",
        search_queries=["EV lifecycle emissions coal grid study"],
    )
    src = Source(
        url="https://example.org/ev-study",
        title="Lifecycle EV Study",
        domain="example.org",
        snapshot_hash="sha256:abc123",
        rank_score=0.9,
        source_type=SourceType.PRIMARY,
    )
    ev = Evidence(
        source_id=src.id,
        quote="In coal-dominated grids, lifecycle parity takes longer.",
        stance=Stance.CONTRADICTS,
        quote_verified=True,
        context_conditions=["coal-heavy grid"],
    )
    finding = Finding(
        subclaim_id="sub-1",
        supporting=[],
        contradicting=[ev.id],
        gaps=[],
        verdict=Verdict.CONDITIONAL,
        confidence=0.85,
    )
    report = Report(
        claim=claim,
        findings=[finding],
        verdict=Verdict.CONDITIONAL,
        limitations=["Limited regional data"],
        citations=[src],
    )

    assert sq.claim_id == claim.id
    assert report.verdict == Verdict.CONDITIONAL
    assert report.citations[0].source_type == SourceType.PRIMARY

    with pytest.raises(ValidationError):
        Source(
            url="https://example.org",
            domain="example.org",
            snapshot_hash="abc",
            rank_score=1.5,
        )


def test_settings_default_budget() -> None:
    """Verify Settings constructs a RunBudget matching its configured caps."""
    settings = Settings(max_llm_tokens=5000, max_searches=3, max_fetches=4, max_loops=1)
    budget = settings.default_budget()
    assert budget.max_llm_tokens == 5000
    assert budget.max_searches == 3
    assert budget.max_fetches == 4
    assert budget.max_loops == 1


def test_budget_governor_limits_and_exhaustion() -> None:
    """Verify BudgetGovernor tracks usage, reports remaining, and raises on overflow."""
    clock = FakeClock()
    budget = RunBudget(
        max_llm_tokens=100,
        max_searches=2,
        max_fetches=3,
        max_loops=1,
        max_seconds=10.0,
    )
    gov = BudgetGovernor(budget, clock=clock)

    assert not gov.exhausted()
    gov.consume("tokens", 60)
    gov.consume("searches", 1)
    assert gov.remaining()["tokens"] == 40
    assert gov.remaining()["searches"] == 1
    assert not gov.exhausted()

    # Hit exact search cap -> exhausted becomes True
    gov.consume("searches", 1)
    assert gov.exhausted()

    # Exceed search cap -> raises BudgetExceeded
    with pytest.raises(BudgetExceededError) as exc_info:
        gov.consume("searches", 1)
    assert exc_info.value.kind == "searches"

    # Exceed token cap -> raises BudgetExceeded and leaves prior token count intact
    with pytest.raises(BudgetExceededError) as exc_info:
        gov.consume("tokens", 41)
    assert exc_info.value.kind == "tokens"
    assert gov.remaining()["tokens"] == 40


def test_budget_governor_time_expiry() -> None:
    """Verify BudgetGovernor enforces wall-clock timeout."""
    clock = FakeClock()
    budget = RunBudget(max_seconds=5.0)
    gov = BudgetGovernor(budget, clock=clock)

    clock.advance(5.5)
    assert gov.exhausted()
    assert gov.remaining()["seconds"] == 0.0

    with pytest.raises(BudgetExceededError) as exc_info:
        gov.consume("fetches", 1)
    assert exc_info.value.kind == "seconds"


def test_budget_governor_thread_safety() -> None:
    """Verify concurrent consume calls never exceed the configured cap."""
    budget = RunBudget(max_fetches=25)
    gov = BudgetGovernor(budget)

    def _try_consume() -> bool:
        try:
            gov.consume("fetches", 1)
            return True
        except BudgetExceededError:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: _try_consume(), range(50)))

    assert sum(results) == 25
    assert gov.remaining()["fetches"] == 0
    assert gov.exhausted()


def test_audit_recorder_ordering_and_sink() -> None:
    """Verify AuditRecorder assigns strictly increasing seq numbers and notifies sink."""
    sink = ListSink()
    recorder = AuditRecorder(run_id="run-123", sink=sink)

    e1 = recorder.record("planner", "plan_created", {"subclaims": 2}, tokens=120)
    e2 = recorder.record("researcher", "search_done", {"hits": 5}, tokens=0)
    e3 = recorder.record("extractor", "quotes_extracted", {"count": 3}, tokens=350)

    events = recorder.events()
    assert [e.seq for e in events] == [1, 2, 3]
    assert [e.node for e in events] == ["planner", "researcher", "extractor"]
    assert recorder.total_tokens() == 470
    assert sink.received == [e1, e2, e3]


def test_audit_recorder_concurrent_ordering() -> None:
    """Verify concurrent record calls produce contiguous, unique sequence numbers."""
    recorder = AuditRecorder(run_id="run-concurrent")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: recorder.record("worker", "step", {"i": i}, tokens=1), range(40)))

    events = recorder.events()
    assert len(events) == 40
    assert [e.seq for e in events] == list(range(1, 41))
    assert recorder.total_tokens() == 40


def test_structured_json_logging_includes_run_id() -> None:
    """Verify JsonLogFormatter outputs valid JSON with context-bound run_id."""
    formatter = JsonLogFormatter()
    token = set_run_id("run-abc-999")
    try:
        record = logging.LogRecord(
            name="veriagent.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Node started",
            args=(),
            exc_info=None,
        )
        record.node = "planner"
        rendered = formatter.format(record)
        data = json.loads(rendered)
        assert data["run_id"] == "run-abc-999"
        assert data["node"] == "planner"
        assert data["message"] == "Node started"
        assert data["level"] == "INFO"
    finally:
        reset_run_id(token)
