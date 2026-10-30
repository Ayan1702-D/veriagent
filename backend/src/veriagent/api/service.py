"""Background graph execution, persistence, replay, and live budget tracking."""

import logging
import threading
from collections.abc import Callable
from typing import Any

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.db.repo import DatabaseAuditSink, RunRepository
from veriagent.graph import GraphState, build_verification_graph
from veriagent.llm.client import LLMProtocol
from veriagent.schemas import Claim, RunBudget
from veriagent.tools.fetch import fetch_url
from veriagent.tools.search.base import SearchProvider

logger = logging.getLogger(__name__)
FetchFunction = Callable[..., Any]


class RunService:
    """Own background verification and replay execution."""

    def __init__(
        self,
        repository: RunRepository,
        llm: LLMProtocol,
        search_providers: list[SearchProvider],
        fetch_fn: FetchFunction = fetch_url,
    ) -> None:
        self.repository = repository
        self._llm = llm
        self._search_providers = search_providers
        self._fetch_fn = fetch_fn
        self._graph = build_verification_graph()
        self._budgets: dict[str, BudgetGovernor] = {}
        self._budget_lock = threading.RLock()

    def budget_usage(self, run_id: str) -> dict[str, float | int]:
        """Return live usage, falling back to the stored final usage."""
        with self._budget_lock:
            governor = self._budgets.get(run_id)
        if governor is not None:
            return governor.usage()
        row = self.repository.get_run(run_id)
        return dict(row.budget_usage_json) if row is not None else {}

    async def execute(self, run_id: str, claim: Claim, budget_spec: RunBudget) -> None:
        """Run the LangGraph pipeline and persist all output."""
        governor = BudgetGovernor(budget_spec)
        recorder = AuditRecorder(run_id, sink=DatabaseAuditSink(self.repository))
        with self._budget_lock:
            self._budgets[run_id] = governor

        self.repository.set_status(run_id, "running", budget_usage=governor.usage())
        recorder.record(
            node="system",
            type="run_started",
            payload={"budget": budget_spec.model_dump(mode="json")},
        )

        initial_state: GraphState = {
            "claim": claim,
            "subquestions": [],
            "sources": [],
            "snapshots": {},
            "evidence": [],
            "findings": [],
            "report": None,
            "loop_count": 0,
            "max_loops": budget_spec.max_loops,
            "has_gaps": False,
            "budget": governor,
            "recorder": recorder,
            "llm": self._llm,
            "search_providers": self._search_providers,
            "fetch_fn": self._fetch_fn,
        }

        try:
            final_state = await self._graph.ainvoke(initial_state)
            report = final_state.get("report")
            if report is None:
                raise RuntimeError("Graph completed without a report")
            self.repository.save_artifacts(
                run_id,
                final_state.get("sources", []),
                final_state.get("snapshots", {}),
                final_state.get("evidence", []),
                report,
            )
            usage = governor.usage()
            recorder.record(
                node="system",
                type="run_completed",
                payload={"verdict": report.verdict.value, "budget_usage": usage},
            )
            self.repository.set_status(run_id, "completed", budget_usage=usage)
        except Exception as exc:
            logger.exception("Verification run %s failed", run_id)
            usage = governor.usage()
            recorder.record(
                node="system",
                type="run_failed",
                payload={"error": str(exc), "budget_usage": usage},
            )
            self.repository.set_status(
                run_id, "failed", error=str(exc), budget_usage=usage
            )
        finally:
            with self._budget_lock:
                self._budgets.pop(run_id, None)

    async def execute_replay(self, run_id: str, source_run_id: str) -> None:
        """Reproduce persisted artifacts without any network or LLM calls."""
        recorder = AuditRecorder(run_id, sink=DatabaseAuditSink(self.repository))
        self.repository.set_status(run_id, "running")
        recorder.record(
            node="system",
            type="replay_started",
            payload={"source_run_id": source_run_id, "network": False},
        )
        try:
            report = self.repository.get_report(source_run_id)
            if report is None:
                raise RuntimeError("Source run has no completed report to replay")
            sources, snapshots = self.repository.get_sources(source_run_id)
            evidence = self.repository.get_evidence(source_run_id)
            self.repository.save_artifacts(run_id, sources, snapshots, evidence, report)
            usage = {
                "tokens": 0,
                "searches": 0,
                "fetches": 0,
                "loops": 0,
                "seconds": 0.0,
            }
            recorder.record(
                node="system",
                type="replay_completed",
                payload={"source_run_id": source_run_id, "budget_usage": usage},
            )
            self.repository.set_status(run_id, "completed", budget_usage=usage)
        except Exception as exc:
            logger.exception("Replay run %s failed", run_id)
            recorder.record(
                node="system", type="run_failed", payload={"error": str(exc)}
            )
            self.repository.set_status(run_id, "failed", error=str(exc))
