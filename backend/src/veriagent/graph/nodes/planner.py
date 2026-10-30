"""Planner node: decomposes claim, detects scope qualifiers, and outputs subquestions."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from veriagent.core.errors import BudgetExceededError
from veriagent.graph.state import GraphState
from veriagent.schemas import SubQuestion

_KNOWN_QUALIFIERS = ("always", "never", "all", "regardless", "none", "every", "only")


class PlannerOutput(BaseModel):
    """Structured plan returned by the LLM."""

    model_config = ConfigDict(extra="forbid")

    qualifiers: list[str] = Field(default_factory=list)
    atomic_subclaims: list[str] = Field(default_factory=list)
    subquestions: list[str] = Field(default_factory=list)
    search_queries: list[list[str]] = Field(default_factory=list)


def run_planner_node(state: GraphState) -> dict[str, Any]:
    """Execute planner step: detect qualifiers, split subclaims, and generate queries."""
    claim = state["claim"]
    llm = state["llm"]
    budget = state["budget"]
    recorder = state.get("recorder")

    claim_lower = claim.text.lower()
    heuristic_qualifiers = [q for q in _KNOWN_QUALIFIERS if q in claim_lower]

    messages = [
        {
            "role": "system",
            "content": (
                "You are the VeriAgent Planner. Decompose the user claim into atomic subclaims, "
                "detect qualifiers ('always', 'regardless', 'all', etc.), and produce 1 to 3 "
                "focused subquestions with 1 to 2 targeted search queries each. "
                "Respond strictly in valid JSON matching the schema."
            ),
        },
        {"role": "user", "content": f"Claim: {claim.text}"},
    ]

    try:
        plan: PlannerOutput = llm.complete(
            node="planner",
            messages=messages,
            response_model=PlannerOutput,
            budget=budget,
            recorder=recorder,
        )
    except BudgetExceededError:
        updated_claim = claim.model_copy(
            update={
                "qualifiers": heuristic_qualifiers,
                "atomic_subclaims": [claim.text],
            }
        )

        fallback_question = SubQuestion(
            claim_id=claim.id,
            question=claim.text,
            search_queries=[claim.text],
        )

        return {
            "claim": updated_claim,
            "subquestions": [fallback_question],
            "budget_exhausted": True,
        }
    merged_qualifiers = list(dict.fromkeys(heuristic_qualifiers + plan.qualifiers))
    updated_claim = claim.model_copy(
        update={
            "qualifiers": merged_qualifiers,
            "atomic_subclaims": plan.atomic_subclaims or [claim.text],
        }
    )

    new_subquestions: list[SubQuestion] = []

    for i, q_text in enumerate(plan.subquestions):
        queries = plan.search_queries[i] if i < len(plan.search_queries) else [q_text]
        new_subquestions.append(
            SubQuestion(
                claim_id=claim.id,
                question=q_text,
                search_queries=queries,
            )
        )

    if not new_subquestions:
        new_subquestions.append(
            SubQuestion(
                claim_id=claim.id,
                question=claim.text,
                search_queries=[claim.text],
            )
        )

    if recorder is not None:
        recorder.record(
            node="planner",
            type="plan_completed",
            payload={
                "qualifiers": merged_qualifiers,
                "subclaims_count": len(updated_claim.atomic_subclaims),
                "subquestions_count": len(new_subquestions),
            },
        )

    return {
        "claim": updated_claim,
        "subquestions": new_subquestions,
    }
