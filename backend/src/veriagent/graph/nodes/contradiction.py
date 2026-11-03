"""Contradiction node: categorizes evidence into agreements, disagreements, and gaps."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from veriagent.core.errors import BudgetExceededError, VeriAgentError
from veriagent.graph.state import GraphState
from veriagent.llm.client import load_prompt
from veriagent.schemas import Finding, Verdict


class SubclaimAnalysis(BaseModel):
    """Analysis for an individual atomic subclaim."""

    model_config = ConfigDict(extra="forbid")

    subclaim: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdict: Verdict = Verdict.INSUFFICIENT
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ContradictionOutput(BaseModel):
    """Contradiction analyst synthesis."""

    model_config = ConfigDict(extra="forbid")

    subclaim_findings: list[SubclaimAnalysis] = Field(default_factory=list)


def run_contradiction_node(state: GraphState) -> dict[str, Any]:
    """Group evidence into supporting, contradicting, and scope gaps across subclaims."""
    claim = state["claim"]
    evidence = state["evidence"]
    llm = state["llm"]
    budget = state["budget"]
    recorder = state.get("recorder")

    if not evidence:
        insufficient_findings = [
            Finding(
                subclaim_id=subclaim,
                gaps=["No verified evidence was retrieved for this subclaim."],
                verdict=Verdict.INSUFFICIENT,
                confidence=0.0,
            )
            for subclaim in (claim.atomic_subclaims or [claim.text])
        ]
        if recorder is not None:
            recorder.record(
                node="contradiction",
                type="analysis_completed",
                payload={
                    "findings_count": len(insufficient_findings),
                    "has_gaps": True,
                    "reason": "no_evidence",
                },
            )
        return {"findings": insufficient_findings, "has_gaps": True}

    evidence_summary = [
        {
            "id": e.id,
            "quote": e.quote,
            "verified": e.quote_verified,
            "stance": e.stance.value,
            "conditions": e.context_conditions,
        }
        for e in evidence
    ]

    messages = [
        {
            "role": "system",
            "content": load_prompt("contradiction"),
        },
        {
            "role": "user",
            "content": (
                f"Claim: {claim.text}\n"
                f"Qualifiers: {claim.qualifiers}\n"
                f"Atomic Subclaims: {claim.atomic_subclaims}\n"
                f"Evidence: {evidence_summary}"
            ),
        },
    ]

    try:
        analysis: ContradictionOutput = llm.complete(
            node="contradiction",
            messages=messages,
            response_model=ContradictionOutput,
            budget=budget,
            recorder=recorder,
        )
    except (BudgetExceededError, VeriAgentError) as exc:
        if recorder is not None:
            recorder.record(
                node="contradiction",
                type="llm_unavailable",
                payload={"reason": type(exc).__name__},
            )
        return {
            "budget_exhausted": isinstance(exc, BudgetExceededError),
            "findings": [
                Finding(
                    subclaim_id=subclaim,
                    gaps=["Evidence analysis could not complete; no verdict was assigned."],
                    verdict=Verdict.INSUFFICIENT,
                    confidence=0.0,
                )
                for subclaim in (claim.atomic_subclaims or [claim.text])
            ],
            "has_gaps": True,
        }

    findings: list[Finding] = []
    has_gaps = False

    for item in analysis.subclaim_findings:
        if item.gaps:
            has_gaps = True
        findings.append(
            Finding(
                subclaim_id=item.subclaim,
                supporting=item.supporting_evidence_ids,
                contradicting=item.contradicting_evidence_ids,
                gaps=item.gaps,
                verdict=item.verdict,
                confidence=item.confidence,
            )
        )

    if recorder is not None:
        recorder.record(
            node="contradiction",
            type="analysis_completed",
            payload={
                "findings_count": len(findings),
                "has_gaps": has_gaps,
            },
        )

    return {
        "findings": findings,
        "has_gaps": has_gaps,
    }
