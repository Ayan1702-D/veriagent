"""Unit tests for L4 verification: quote matching, entailment, and unsupported claims."""

import pytest

from veriagent.llm.fake import FakeLLM
from veriagent.schemas import Evidence, Finding, Stance, Verdict
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


@pytest.mark.parametrize(
    "verdict,supports,contradicts,expected",
    [
        (Verdict.SUPPORTED, True, False, Verdict.SUPPORTED),
        (Verdict.SUPPORTED, False, True, Verdict.INSUFFICIENT),
        (Verdict.REFUTED, False, True, Verdict.REFUTED),
        (Verdict.REFUTED, True, False, Verdict.INSUFFICIENT),
        (Verdict.MIXED, True, True, Verdict.MIXED),
        (Verdict.MIXED, True, False, Verdict.INSUFFICIENT),
        (Verdict.CONDITIONAL, False, True, Verdict.CONDITIONAL),
        (Verdict.CONDITIONAL, True, False, Verdict.CONDITIONAL),
        (Verdict.CONDITIONAL, False, False, Verdict.INSUFFICIENT),
        (Verdict.INSUFFICIENT, True, True, Verdict.INSUFFICIENT),
    ],
)
def test_unsupported_claim_rule_enforcement(
    verdict: Verdict,
    supports: bool,
    contradicts: bool,
    expected: Verdict,
) -> None:
    """Only verified IDs linked in the correct finding direction authorize verdicts."""
    evidence = Evidence(source_id="s1", quote="Verified evidence", quote_verified=True)
    finding = Finding(
        subclaim_id="claim",
        verdict=verdict,
        supporting=[evidence.id] if supports else [],
        contradicting=[evidence.id] if contradicts else [],
    )
    assert apply_unsupported_claim_rule(finding, [evidence]) == expected
    assert apply_unsupported_claim_rule(finding, []) == Verdict.INSUFFICIENT
    assert (
        apply_unsupported_claim_rule(
            finding, [evidence.model_copy(update={"quote_verified": False})]
        )
        == Verdict.INSUFFICIENT
    )


@pytest.mark.parametrize(
    "quote,snapshot",
    [
        ("The reduction was 40 percent.", "The reduction was 90 percent."),
        ("40 percent", "140 percent"),
        ("It was 5 degrees", "It was -5 degrees"),
        ("Travel for 70,000 kilometers", "Travel for 90,000 kilometers"),
        ("Temperature reached 1.5 degrees", "Temperature reached 1.8 degrees"),
    ],
)
def test_quote_match_rejects_changed_numeric_tokens(quote: str, snapshot: str) -> None:
    """Similar prose cannot conceal a changed number, even at a low threshold."""
    assert not verify_quote(quote, snapshot, threshold=50).found


def test_quote_match_uses_configured_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured threshold controls fuzzy matches when no override is supplied."""
    from veriagent.config import get_settings

    monkeypatch.setattr(get_settings(), "quote_match_threshold", 100.0)
    assert not verify_quote("The car is blue.", "The car is bluu.").found
    assert verify_quote("The car is blue.", "The car is bluu.", threshold=70).found


def test_quote_match_finds_valid_number_after_invalid_substring() -> None:
    """A preceding larger number cannot hide a later exact quote."""
    assert verify_quote("40 percent", "140 percent previously; 40 percent now").found


def test_entailment_omissions_do_not_reuse_extractor_stance() -> None:
    """Missing entailment decisions remain neutral for that finding."""
    evidence = Evidence(
        source_id="source",
        quote="A verified quotation.",
        quote_verified=True,
        stance=Stance.SUPPORTS,
    )
    updated = check_support("Test conclusion", [evidence], FakeLLM({"verifier": {}}))
    assert updated[0].stance == Stance.NEUTRAL
    assert evidence.stance == Stance.SUPPORTS
