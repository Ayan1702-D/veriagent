"""Extractor node: extracts quotes, dates, stance, and runs deterministic quote_match."""

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from veriagent.config import get_settings
from veriagent.core.errors import BudgetExceededError, VeriAgentError
from veriagent.graph.state import GraphState
from veriagent.llm.client import load_prompt
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

    extracted_ids = set(state.get("extracted_source_ids", []))
    extracted_ids.update(e.source_id for e in existing_evidence)
    new_evidence: list[Evidence] = []
    analysis_time_reserve = float(budget.remaining()["seconds"]) / 2

    for src in sources:
        if src.id in extracted_ids:
            continue
        remaining = budget.remaining()
        if remaining["tokens"] <= 0 or remaining["seconds"] <= analysis_time_reserve:
            break
        text = snapshots.get(src.id, "")
        if not text:
            continue

        truncated_context = text[:3500]
        messages = [
            {
                "role": "system",
                "content": load_prompt("extractor"),
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
        except VeriAgentError as exc:
            if recorder is not None:
                recorder.record(
                    node="extractor",
                    type="llm_unavailable",
                    payload={"source_id": src.id, "reason": type(exc).__name__},
                )
            continue

        extracted_ids.add(src.id)
        for item in resp.items:
            # Deterministic quote verification against the un-truncated full snapshot
            match_res = verify_quote(
                item.quote, text, threshold=get_settings().quote_match_threshold
            )

            stance_norm = item.stance.strip().lower()
            if stance_norm == "supports":
                stance_val = Stance.SUPPORTS
            elif stance_norm == "contradicts":
                stance_val = Stance.CONTRADICTS
            else:
                stance_val = Stance.NEUTRAL

            new_evidence.append(
                Evidence(
                    id=hashlib.sha256(f"{src.id}\0{item.quote.strip()}".encode()).hexdigest()[:32],
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
    by_quote: dict[tuple[str, str], Evidence] = {}
    for evidence in combined:
        by_quote.setdefault((evidence.source_id, evidence.quote.strip()), evidence)
    unique_evidence = list(by_quote.values())

    if recorder is not None:
        recorder.record(
            node="extractor",
            type="extraction_completed",
            payload={
                "extracted_count": len(new_evidence),
                "verified_quotes_count": sum(1 for e in unique_evidence if e.quote_verified),
            },
        )

    return {"evidence": list(unique_evidence), "extracted_source_ids": sorted(extracted_ids)}
