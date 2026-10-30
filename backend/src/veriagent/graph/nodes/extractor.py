"""Extractor node: extracts quotes, dates, stance, and runs deterministic quote_match."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from veriagent.core.errors import BudgetExceededError
from veriagent.graph.state import GraphState
from veriagent.schemas import Evidence, Stance
from veriagent.verification.quote_match import verify_quote


class RawExtractedEvidence(BaseModel):
    """Single evidence quote item returned by the extractor LLM."""

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=3)
    date: str | None = None
    stance: str = Field(default="neutral")
    context_conditions: list[str] = Field(default_factory=list)


class ExtractorOutput(BaseModel):
    """Batch of extracted evidence quotes."""

    model_config = ConfigDict(extra="forbid")

    items: list[RawExtractedEvidence] = Field(default_factory=list)


def run_extractor_node(state: GraphState) -> dict[str, Any]:
    """Extract quotes from source snapshots and verify verbatim presence deterministically."""
    sources = state["sources"]
    snapshots = state["snapshots"]
    llm = state["llm"]
    budget = state["budget"]
    recorder = state.get("recorder")
    existing_evidence = list(state.get("evidence", []))

    new_evidence: list[Evidence] = []

    for src in sources:
        if budget.exhausted():
            break
        text = snapshots.get(src.id, "")
        if not text:
            continue

        truncated_context = text[:3500]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the VeriAgent Extractor. Extract verbatim quotes "
                    "relevant to the claim, detect publication date, stance "
                    "(supports, contradicts, neutral), and any context conditions "
                    "(e.g. grid mix, region). Do NOT paraphrase quotes. "
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Claim: {state['claim'].text}\n"
                    f"Source: {src.url}\n\nDocument Text:\n{truncated_context}"
                ),
            },
        ]

        try:
            resp: ExtractorOutput = llm.complete(
                node="extractor",
                messages=messages,
                response_model=ExtractorOutput,
                budget=budget,
                recorder=recorder,
            )
        except BudgetExceededError:
            break

        for item in resp.items:
            # Deterministic quote verification against the un-truncated full snapshot
            match_res = verify_quote(item.quote, text, threshold=85.0)

            stance_norm = item.stance.strip().lower()
            if stance_norm == "supports":
                stance_val = Stance.SUPPORTS
            elif stance_norm == "contradicts":
                stance_val = Stance.CONTRADICTS
            else:
                stance_val = Stance.NEUTRAL

            new_evidence.append(
                Evidence(
                    source_id=src.id,
                    quote=item.quote,
                    date=item.date,
                    stance=stance_val,
                    quote_verified=match_res.found,
                    context_conditions=item.context_conditions,
                )
            )

    combined = existing_evidence + new_evidence
    # Deduplicate exact quotes
    unique_evidence = {e.quote.strip(): e for e in combined}.values()

    if recorder is not None:
        recorder.record(
            node="extractor",
            type="extraction_completed",
            payload={
                "extracted_count": len(new_evidence),
                "verified_quotes_count": sum(1 for e in unique_evidence if e.quote_verified),
            },
        )

    return {"evidence": list(unique_evidence)}
