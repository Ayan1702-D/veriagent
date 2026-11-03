"""Reporter node: produces final Report with citations mapped strictly to fetched sources."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from veriagent.core.errors import BudgetExceededError, VeriAgentError
from veriagent.graph.state import GraphState
from veriagent.llm.client import load_prompt
from veriagent.schemas import Report, Verdict
from veriagent.verification.entailment import apply_unsupported_claim_rule


class ReporterLLMOutput(BaseModel):
    """Structured report synthesis output."""

    model_config = ConfigDict(extra="forbid")

    overall_verdict: Verdict
    limitations: list[str] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)


def run_reporter_node(state: GraphState) -> dict[str, Any]:
    """Generate final comprehensive Report citing stored URLs and detailing limitations."""
    claim = state["claim"]
    findings = state["findings"]
    sources = state["sources"]
    budget = state["budget"]
    llm = state["llm"]
    recorder = state.get("recorder")

    findings = [
        f.model_copy(update={"verdict": apply_unsupported_claim_rule(f, state["evidence"])})
        for f in findings
    ]
    referenced_ids = {eid for f in findings for eid in f.supporting + f.contradicting}
    verified_source_ids = {
        e.source_id for e in state["evidence"] if e.quote_verified and e.id in referenced_ids
    }
    verified_sources = [source for source in sources if source.id in verified_source_ids]
    verdicts = {f.verdict for f in findings}
    if not verdicts or Verdict.INSUFFICIENT in verdicts:
        overall = Verdict.INSUFFICIENT
    elif len(verdicts) == 1:
        overall = next(iter(verdicts))
    elif Verdict.CONDITIONAL in verdicts:
        overall = Verdict.CONDITIONAL
    else:
        overall = Verdict.MIXED
    model_unavailable = recorder is not None and any(
        event.type == "llm_unavailable" for event in recorder.events()
    )

    # Search and fetch caps do not prevent synthesis from evidence already stored.
    remaining = budget.remaining()
    if (
        state.get("budget_exhausted", False)
        or remaining["tokens"] <= 0
        or remaining["seconds"] <= 0
    ):
        depleted = [
            label
            for key, label in (("tokens", "model tokens"), ("seconds", "time"))
            if remaining[key] <= 0
        ]
        detail = ", ".join(depleted) if depleted else "a run resource"
        limitations = [f"Run reached its {detail} limit; report uses partial data."]
        if not verified_sources:
            limitations.append(
                "No verified evidence linked to findings was available; "
                "the claim could not be assessed."
            )
        if model_unavailable:
            limitations.append("One or more model calls failed; the assessment is incomplete.")
        report = Report(
            claim=claim,
            findings=findings,
            verdict=overall,
            limitations=limitations,
            citations=verified_sources,
        )
        return {"report": report}

    if not verified_sources:
        limitation = (
            "No accessible source pages were retrieved; the claim could not be assessed."
            if not sources
            else "Source pages yielded no verified quote for this claim."
        )
        limitations = [limitation]
        if model_unavailable:
            limitations.append("One or more model calls failed; the assessment is incomplete.")
        report = Report(
            claim=claim,
            findings=findings,
            verdict=Verdict.INSUFFICIENT,
            limitations=limitations,
        )
        if recorder is not None:
            recorder.record(
                node="reporter",
                type="report_completed",
                payload={
                    "verdict": report.verdict.value,
                    "citations_count": 0,
                    "reason": "no_evidence",
                },
            )
        return {"report": report}

    messages = [
        {
            "role": "system",
            "content": load_prompt("reporter"),
        },
        {
            "role": "user",
            "content": (
                f"Claim: {claim.text}\n"
                f"Qualifiers: {claim.qualifiers}\n"
                f"Findings: {[f.model_dump() for f in findings]}\n"
                f"Available Sources: "
                f"{[{'id': s.id, 'url': s.url, 'title': s.title} for s in sources]}"
            ),
        },
    ]

    try:
        out: ReporterLLMOutput = llm.complete(
            node="reporter",
            messages=messages,
            response_model=ReporterLLMOutput,
            budget=budget,
            recorder=recorder,
        )
    except (BudgetExceededError, VeriAgentError) as exc:
        if recorder is not None:
            recorder.record(
                node="reporter",
                type="llm_unavailable",
                payload={"reason": type(exc).__name__},
            )
        return {
            "report": Report(
                claim=claim,
                findings=findings,
                verdict=overall,
                limitations=["Report synthesis could not complete; report uses partial data."],
                citations=verified_sources,
            )
        }

    report = Report(
        claim=claim,
        findings=findings,
        verdict=overall,
        limitations=out.limitations,
        citations=verified_sources,
    )

    if recorder is not None:
        recorder.record(
            node="reporter",
            type="report_completed",
            payload={"verdict": report.verdict.value, "citations_count": len(verified_sources)},
        )

    return {"report": report}
