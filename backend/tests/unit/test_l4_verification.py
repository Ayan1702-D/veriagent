"""Unit tests for L4 verification: quote matching, entailment, and unsupported claims."""

from veriagent.llm.fake import FakeLLM
from veriagent.schemas import Evidence, Stance, Verdict
from veriagent.verification import (
    apply_unsupported_claim_rule,
    build_counter_queries,
    check_support,
    verify_quote,
)

SAMPLE_SNAPSHOT = """
Climate Research Institute Report (2025):
In coal-dominated power grids (such as Poland or parts of China), the lifetime carbon
emissions of electric vehicles remain roughly comparable to high-efficiency diesel hybrids
for the first 70,000 kilometers of driving. However, in regions where renewable or nuclear
generation exceeds 40%, lifecycle emissions are substantially lower from year one.
"""


def test_quote_match_exact_and_spans() -> None:
    """Verify exact quote returns 100.0 score and correct span."""
    quote = "In coal-dominated power grids \n (such as ‘Poland’ or parts of China)"  # noqa: RUF001
    res = verify_quote(quote, SAMPLE_SNAPSHOT)
    assert res.found is True
    assert res.score == 100.0
    assert res.span is not None
    assert res.span[0] < res.span[1]


def test_quote_match_whitespace_case_and_curly_punctuation() -> None:
    """Verify quote with line-breaks, extra spacing, and curly quotes matches."""
    # Modified quote with extra spaces, newline, different quote chars
    quote = "In coal-dominated power grids \n (such as ‘Poland’ or parts of China)"  # noqa: RUF001
    res = verify_quote(quote, SAMPLE_SNAPSHOT, threshold=85.0)
    assert res.found is True
    assert res.score >= 85.0


def test_quote_match_fabricated_quote() -> None:
    """Verify fabricated or hallucinated quote fails verification."""
    fake_quote = (
        "Electric vehicles permanently produce 99% higher toxic emissions regardless of grid."
    )
    res = verify_quote(fake_quote, SAMPLE_SNAPSHOT, threshold=80.0)
    assert res.found is False
    assert res.score < 80.0
    assert res.span is None


def test_check_support_evaluates_only_verified_evidence() -> None:
    """Verify entailment only submits verified quotes and updates stances."""
    ev_verified = Evidence(
        id="ev-1",
        source_id="src-1",
        quote="In coal-dominated power grids, emissions remain comparable.",
        quote_verified=True,
    )
    ev_unverified = Evidence(
        id="ev-2",
        source_id="src-2",
        quote="Unverified claim about electric battery manufacturing.",
        quote_verified=False,
    )

    fake_llm = FakeLLM(
        responses={
            "verifier": {
                "evaluations": [
                    {
                        "evidence_id": "ev-1",
                        "label": "supports",
                        "reason": "Directly corroborates the grid mix dependency.",
                    }
                ]
            }
        }
    )

    updated = check_support(
        conclusion="EV lifecycle emissions depend heavily on grid composition.",
        evidence_list=[ev_verified, ev_unverified],
        llm=fake_llm,
    )

    assert len(updated) == 2
    assert updated[0].id == "ev-1"
    assert updated[0].stance == Stance.SUPPORTS
    assert updated[1].id == "ev-2"
    assert updated[1].stance == Stance.NEUTRAL  # Remained unverified/untouched


def test_build_counter_queries() -> None:
    """Verify adversarial query generator returns search strings."""
    fake_llm = FakeLLM(
        responses={
            "verifier": {
                "queries": [
                    "electric vehicles coal grid parity emissions",
                    "lifecycle emissions EV vs diesel heavy coal",
                ]
            }
        }
    )

    queries = build_counter_queries("EVs always produce lower emissions", llm=fake_llm)
    assert len(queries) == 2
    assert "coal" in queries[0]


def test_unsupported_claim_rule_enforcement() -> None:
    """Verify conclusion with zero verified supporting quotes defaults to INSUFFICIENT."""
    # 1. Unverified evidence marked SUPPORTS -> must still become INSUFFICIENT
    ev_unverified = Evidence(
        source_id="s1",
        quote="EVs are always green",
        stance=Stance.SUPPORTS,
        quote_verified=False,
    )
    assert apply_unsupported_claim_rule(Verdict.SUPPORTED, [ev_unverified]) == Verdict.INSUFFICIENT

    # 2. Verified evidence marked CONTRADICTS -> must become INSUFFICIENT for SUPPORTED verdict
    ev_contradicting = Evidence(
        source_id="s1",
        quote="EVs emit more in coal grids",
        stance=Stance.CONTRADICTS,
        quote_verified=True,
    )
    assert (
        apply_unsupported_claim_rule(Verdict.SUPPORTED, [ev_contradicting]) == Verdict.INSUFFICIENT
    )

    # 3. Verified evidence marked SUPPORTS -> retains tentative verdict
    ev_supporting = Evidence(
        source_id="s1",
        quote="Renewable grids yield instant reductions",
        stance=Stance.SUPPORTS,
        quote_verified=True,
    )
    assert apply_unsupported_claim_rule(Verdict.CONDITIONAL, [ev_supporting]) == Verdict.CONDITIONAL
