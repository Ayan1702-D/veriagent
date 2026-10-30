"""Verifier node: entailment checks, adversarial counter-search, and verdict downgrade."""

from typing import Any

from veriagent.graph.state import GraphState
from veriagent.schemas import Finding, SubQuestion, Verdict
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

    updated_evidence = list(evidence)
    calibrated_findings: list[Finding] = []
    adversarial_questions: list[SubQuestion] = []

    for finding in findings:
        subclaim_text = finding.subclaim_id

        # 1. Re-verify entailment using cheap model
        updated_evidence = check_support(
            conclusion=subclaim_text,
            evidence_list=updated_evidence,
            llm=llm,
            budget=budget,
            recorder=recorder,
        )

        # 2. Strict unsupported claim rule: 0 verified supporting quotes -> INSUFFICIENT
        final_sub_verdict = apply_unsupported_claim_rule(finding.verdict, updated_evidence)

        # 3. Check scope qualifiers against valid counter-evidence.
        if any(q in ("always", "regardless", "all") for q in claim.qualifiers):
            has_contradiction = any(
                e.quote_verified and e.stance.value == "contradicts" for e in updated_evidence
            )
            if has_contradiction and final_sub_verdict == Verdict.SUPPORTED:
                final_sub_verdict = Verdict.CONDITIONAL

        calibrated_findings.append(finding.model_copy(update={"verdict": final_sub_verdict}))

        # 4. Adversarial counter-queries if tentative verdict was SUPPORTED and gaps remain
        if final_sub_verdict == Verdict.SUPPORTED and not budget.exhausted():
            counter_queries = build_counter_queries(
                conclusion=subclaim_text,
                llm=llm,
                budget=budget,
                recorder=recorder,
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

    return {
        "evidence": updated_evidence,
        "findings": calibrated_findings,
        "subquestions": combined_questions,
        "loop_count": state["loop_count"] + 1,
    }
