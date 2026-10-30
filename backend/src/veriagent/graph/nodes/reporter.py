"""Reporter node: produces final Report with citations mapped strictly to fetched sources."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from veriagent.graph.state import GraphState
from veriagent.schemas import Report, Source, Verdict


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

    source_by_id = {s.id: s for s in sources}
    source_by_url = {s.url: s for s in sources}

    # If budget is completely exhausted, produce partial report with clear limitations
    if state.get("budget_exhausted", False) or budget.exhausted():
        limitations = [
            "Run budget reached hard limits (tokens/searches/time); "
            "report generated from partial data."
        ]
        # Calibrate overall verdict conservatively
        verdicts = [f.verdict for f in findings]
        overall = Verdict.CONDITIONAL if Verdict.CONDITIONAL in verdicts else Verdict.INSUFFICIENT
        report = Report(
            claim=claim,
            findings=findings,
            verdict=overall,
            limitations=limitations,
            citations=sources[:5],
        )
        return {"report": report}

    messages = [
        {
            "role": "system",
            "content": (
                "You are the VeriAgent Reporter. Synthesize findings into "
                "a final calibrated verdict "
                "(SUPPORTED, REFUTED, MIXED, CONDITIONAL, INSUFFICIENT). "
                "List explicit limitations and select the source IDs that "
                "directly substantiate the findings. "
            ),
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

    out: ReporterLLMOutput = llm.complete(
        node="reporter",
        messages=messages,
        response_model=ReporterLLMOutput,
        budget=budget,
        recorder=recorder,
    )

    # Every citation MUST point to a verified, fetched Source object
    citations: list[Source] = []
    for sid in out.cited_source_ids:
        if sid in source_by_id:
            citations.append(source_by_id[sid])
        elif sid in source_by_url:
            citations.append(source_by_url[sid])

    if not citations and sources:
        citations = sources[:3]

    report = Report(
        claim=claim,
        findings=findings,
        verdict=out.overall_verdict,
        limitations=out.limitations,
        citations=citations,
    )

    if recorder is not None:
        recorder.record(
            node="reporter",
            type="report_completed",
            payload={"verdict": report.verdict.value, "citations_count": len(citations)},
        )

    return {"report": report}
