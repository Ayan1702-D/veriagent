"""State representation passed through the LangGraph verification pipeline."""

from typing import Any, NotRequired, TypedDict

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.llm.client import LLMProtocol
from veriagent.schemas import (
    Claim,
    Evidence,
    Finding,
    Report,
    Source,
    SubQuestion,
)
from veriagent.tools.search.base import SearchProvider


class GraphState(TypedDict):
    """Execution state schema for the VeriAgent multi-agent graph."""

    # Core state models
    claim: Claim
    subquestions: list[SubQuestion]
    sources: list[Source]
    snapshots: dict[str, str]  # source_id -> raw clean text snapshot
    evidence: list[Evidence]
    findings: list[Finding]
    report: Report | None

    # Loop control & budget tracking
    loop_count: int
    max_loops: int
    has_gaps: bool
    budget_exhausted: NotRequired[bool]
    budget: BudgetGovernor
    recorder: AuditRecorder | None

    # Pluggable runtime dependencies
    llm: LLMProtocol
    search_providers: list[SearchProvider]
    fetch_fn: Any  # Callable[[str, ...], Awaitable[FetchedDocument]]
