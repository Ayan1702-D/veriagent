"""LangGraph pipeline compilation and runner helper."""

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from veriagent.graph.edges import (
    should_research_after_planning,
    should_research_or_report,
)
from veriagent.graph.nodes import (
    run_contradiction_node,
    run_extractor_node,
    run_planner_node,
    run_reporter_node,
    run_researcher_node,
    run_verifier_node,
)
from veriagent.graph.state import GraphState


def build_verification_graph() -> CompiledStateGraph[GraphState, Any, GraphState, GraphState]:
    """Build and compile the multi-agent fact verification LangGraph."""
    workflow = StateGraph(GraphState)

    # Register workflow nodes
    workflow.add_node("planner", run_planner_node)
    workflow.add_node("researcher", run_researcher_node)
    workflow.add_node("extractor", run_extractor_node)
    workflow.add_node("contradiction", run_contradiction_node)
    workflow.add_node("verifier", run_verifier_node)
    workflow.add_node("reporter", run_reporter_node)

    workflow.set_entry_point("planner")

    # Route directly to reporter if planner exhausts the budget
    workflow.add_conditional_edges(
        "planner",
        should_research_after_planning,
        {
            "researcher": "researcher",
            "reporter": "reporter",
        },
    )

    workflow.add_edge("researcher", "extractor")
    workflow.add_edge("extractor", "contradiction")
    workflow.add_edge("contradiction", "verifier")

    workflow.add_conditional_edges(
        "verifier",
        should_research_or_report,
        {
            "researcher": "researcher",
            "reporter": "reporter",
        },
    )

    workflow.add_edge("reporter", END)

    return workflow.compile()
