"""LLM-assisted entailment check and adversarial search query generation."""

from pydantic import BaseModel, ConfigDict, Field

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.llm.client import LLMProtocol, load_prompt
from veriagent.schemas import Evidence, Finding, Stance, Verdict


class EntailmentItem(BaseModel):
    """Support assessment for a single piece of evidence."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    label: str = Field(description="Must be 'supports', 'contradicts', or 'not_related'")
    reason: str = Field(min_length=3, max_length=500)


class EntailmentResponse(BaseModel):
    """Collection of entailment decisions for evaluated evidence items."""

    model_config = ConfigDict(extra="forbid")

    evaluations: list[EntailmentItem] = Field(default_factory=list)


class CounterQueriesResponse(BaseModel):
    """Adversarial counter-queries intended to falsify a conclusion."""

    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(default_factory=list)


def check_support(
    conclusion: str,
    evidence_list: list[Evidence],
    llm: LLMProtocol,
    budget: BudgetGovernor | None = None,
    recorder: AuditRecorder | None = None,
) -> list[Evidence]:
    """Check entailment against verified quotes using cheap model; update evidence stance."""
    # Strict rule: Only evaluate items whose quotes were already verified deterministically
    eligible = [e for e in evidence_list if e.quote_verified]
    if not eligible:
        return evidence_list

    prompt_items = [
        {"id": e.id, "quote": e.quote, "conditions": e.context_conditions} for e in eligible
    ]

    messages = [
        {
            "role": "system",
            "content": load_prompt("verifier") + " Evaluate each quote against the conclusion.",
        },
        {
            "role": "user",
            "content": f"Conclusion: {conclusion}\nEvidence items: {prompt_items}",
        },
    ]

    response = llm.complete(
        node="verifier",
        messages=messages,
        response_model=EntailmentResponse,
        budget=budget,
        recorder=recorder,
    )

    eval_by_id = {item.evidence_id: item for item in response.evaluations}

    updated: list[Evidence] = []
    for ev in evidence_list:
        if ev.id in eval_by_id:
            res = eval_by_id[ev.id]
            norm_label = res.label.strip().lower()
            if norm_label == "supports":
                new_stance = Stance.SUPPORTS
            elif norm_label == "contradicts":
                new_stance = Stance.CONTRADICTS
            else:
                new_stance = Stance.NEUTRAL
            updated.append(ev.model_copy(update={"stance": new_stance}))
        elif ev.quote_verified:
            updated.append(ev.model_copy(update={"stance": Stance.NEUTRAL}))
        else:
            updated.append(ev)

    return updated


def build_counter_queries(
    conclusion: str,
    llm: LLMProtocol,
    budget: BudgetGovernor | None = None,
    recorder: AuditRecorder | None = None,
) -> list[str]:
    """Generate adversarial search queries designed to find evidence refuting the conclusion."""
    messages = [
        {
            "role": "system",
            "content": load_prompt("verifier") + " Generate 2 to 4 counter-evidence queries.",
        },
        {"role": "user", "content": f"Tentative Conclusion: {conclusion}"},
    ]

    res = llm.complete(
        node="verifier",
        messages=messages,
        response_model=CounterQueriesResponse,
        budget=budget,
        recorder=recorder,
    )
    return res.queries


def apply_unsupported_claim_rule(finding: Finding, evidence_list: list[Evidence]) -> Verdict:
    """Require verified evidence linked to this finding in each verdict's direction."""
    verified = {e.id for e in evidence_list if e.quote_verified}
    supports = bool(verified.intersection(finding.supporting))
    contradicts = bool(verified.intersection(finding.contradicting))
    allowed = {
        Verdict.SUPPORTED: supports,
        Verdict.REFUTED: contradicts,
        Verdict.MIXED: supports and contradicts,
        Verdict.CONDITIONAL: supports or contradicts,
    }
    return finding.verdict if allowed.get(finding.verdict, False) else Verdict.INSUFFICIENT
