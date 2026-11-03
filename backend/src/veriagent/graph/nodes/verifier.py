"""Verifier node: entailment checks, adversarial counter-search, and verdict downgrade."""

from typing import Any

from veriagent.core.errors import BudgetExceededError, VeriAgentError
from veriagent.graph.state import GraphState
from veriagent.schemas import Finding, Stance, SubQuestion, Verdict
from veriagent.verification.entailment import (
    apply_unsupported_claim_rule,
    build_counter_queries,
    check_support,
)


def run_verifier_node(state: GraphState) -> dict[str, Any]:
    """Execute adversarial check and entailment validation on tentative findings."""
    claim = state["claim"]
    evidence = state["evidence"]
    findings = state["findings"]
    llm = state["llm"]
    budget = state["budget"]
    recorder = state.get("recorder")

    budget_exhausted = state.get("budget_exhausted", False)
    calibrated_findings: list[Finding] = []
    adversarial_questions: list[SubQuestion] = []

    for finding in findings:
        subclaim_text = finding.subclaim_id

        # 1. Re-verify entailment using cheap model
        entailment_failed = False
        try:
            linked_ids = set(finding.supporting + finding.contradicting)
            checked_evidence = check_support(
                conclusion=subclaim_text,
                evidence_list=[e for e in evidence if e.id in linked_ids],
                llm=llm,
                budget=budget,
                recorder=recorder,
            )
        except (BudgetExceededError, VeriAgentError) as exc:
            entailment_failed = True
            budget_exhausted = budget_exhausted or isinstance(exc, BudgetExceededError)
            if recorder is not None:
                recorder.record(
                    node="verifier",
                    type="llm_unavailable",
                    payload={"reason": type(exc).__name__},
                )

        if not entailment_failed:
            finding = finding.model_copy(
                update={
                    "supporting": [
                        e.id
                        for e in checked_evidence
                        if e.quote_verified and e.stance == Stance.SUPPORTS
                    ],
                    "contradicting": [
                        e.id
                        for e in checked_evidence
                        if e.quote_verified and e.stance == Stance.CONTRADICTS
                    ],
                }
            )

        # Calibrate using links belonging only to this finding.
        final_sub_verdict = (
            Verdict.INSUFFICIENT
            if entailment_failed
            else apply_unsupported_claim_rule(finding, evidence)
        )

        # 3. Check scope qualifiers against valid counter-evidence.
        if any(q in ("always", "regardless", "all") for q in claim.qualifiers):
            has_contradiction = any(
                e.quote_verified and e.stance == Stance.CONTRADICTS
                for e in checked_evidence
                if e.id in finding.contradicting
            )
            if has_contradiction and final_sub_verdict == Verdict.SUPPORTED:
                final_sub_verdict = Verdict.CONDITIONAL

        calibrated_findings.append(
            finding.model_copy(
                update={
                    "verdict": final_sub_verdict,
                    "confidence": 0.0
                    if final_sub_verdict == Verdict.INSUFFICIENT
                    else finding.confidence,
                }
            )
        )

        # 4. Adversarial counter-queries if tentative verdict was SUPPORTED and gaps remain
        if final_sub_verdict == Verdict.SUPPORTED and not budget.exhausted():
            try:
                counter_queries = build_counter_queries(
                    conclusion=subclaim_text,
                    llm=llm,
                    budget=budget,
                    recorder=recorder,
                )
            except (BudgetExceededError, VeriAgentError) as exc:
                budget_exhausted = budget_exhausted or isinstance(exc, BudgetExceededError)
                counter_queries = []
                if recorder is not None:
                    recorder.record(
                        node="verifier",
                        type="llm_unavailable",
                        payload={"reason": type(exc).__name__},
                    )
            if counter_queries:
                adversarial_questions.append(
                    SubQuestion(
                        claim_id=claim.id,
                        question=f"Counter-evidence for: {subclaim_text}",
                        search_queries=counter_queries,
                    )
                )

    # Append counter-questions to subquestions so researcher can target them if looping back
    combined_questions = state["subquestions"] + adversarial_questions

    if recorder is not None:
        recorder.record(
            node="verifier",
            type="verification_completed",
            payload={
                "counter_queries_added": len(adversarial_questions),
                "calibrated_verdicts": [f.verdict.value for f in calibrated_findings],
            },
        )

    try:
        budget.consume("loops")
    except BudgetExceededError:
        budget_exhausted = True

    return {
        "budget_exhausted": budget_exhausted,
        "evidence": evidence,
        "findings": calibrated_findings,
        "subquestions": combined_questions,
        "loop_count": state["loop_count"] + 1,
    }
