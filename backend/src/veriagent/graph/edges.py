"""Conditional routing logic for the VeriAgent graph."""

from typing import Literal

from veriagent.graph.state import GraphState


def should_research_after_planning(
    state: GraphState,
) -> Literal["researcher", "reporter"]:
    """Route to reporter if planning exhausted the budget."""
    if state.get("budget_exhausted", False) or state["budget"].exhausted():
        return "reporter"

    return "researcher"


def should_research_or_report(
    state: GraphState,
) -> Literal["researcher", "reporter"]:
    """Control research loops and route exhausted runs to reporting."""
    if state.get("budget_exhausted", False) or state["budget"].exhausted():
        return "reporter"

    has_gaps = state.get("has_gaps", False)
    loop_count = state.get("loop_count", 0)
    max_loops = state.get("max_loops", 1)

    if has_gaps and loop_count < max_loops:
        return "researcher"

    return "reporter"
