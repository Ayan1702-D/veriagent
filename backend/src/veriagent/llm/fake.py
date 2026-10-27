"""Deterministic FakeLLM for unit and integration testing without network calls."""

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor

T = TypeVar("T", bound=BaseModel)


class FakeLLM:
    """Returns canned responses per node and reports token usage to budget and audit recorder."""

    def __init__(
        self,
        responses: dict[str, dict[str, Any] | BaseModel | list[dict[str, Any] | BaseModel]]
        | None = None,
        tokens_per_call: int = 25,
    ) -> None:
        """Initialize with a mapping of node -> canned dict/BaseModel (or list of them)."""
        self._responses = dict(responses) if responses is not None else {}
        self._tokens_per_call = max(0, tokens_per_call)
        self._call_counts: dict[str, int] = {}
        self.calls: list[dict[str, Any]] = []

    def register(
        self,
        node: str,
        response: dict[str, Any] | BaseModel | list[dict[str, Any] | BaseModel],
    ) -> None:
        """Register or override the canned response for `node`."""
        self._responses[node] = response
        self._call_counts[node] = 0

    def complete(
        self,
        node: str,
        messages: list[dict[str, str]],
        response_model: type[T],
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> T:
        """Validate canned node output against `response_model` and record budget/audit."""
        if node not in self._responses:
            raise KeyError(f"FakeLLM has no canned response registered for node={node!r}")

        idx = self._call_counts.get(node, 0)
        self._call_counts[node] = idx + 1
        entry = self._responses[node]

        if isinstance(entry, list):
            if not entry:
                raise ValueError(f"Empty response list registered for node={node!r}")
            selected = entry[min(idx, len(entry) - 1)]
        else:
            selected = entry

        if budget is not None:
            budget.consume("tokens", self._tokens_per_call)

        if recorder is not None:
            recorder.record(
                node=node,
                type="llm_call",
                payload={
                    "model": "fake/deterministic",
                    "attempt": 1,
                    "cached": False,
                    "response_model": response_model.__name__,
                },
                tokens=self._tokens_per_call,
            )

        self.calls.append(
            {
                "node": node,
                "messages": [dict(m) for m in messages],
                "response_model": response_model.__name__,
            }
        )

        if isinstance(selected, BaseModel):
            return response_model.model_validate_json(selected.model_dump_json())

        raw_json = json.dumps(selected)
        return response_model.model_validate_json(raw_json)