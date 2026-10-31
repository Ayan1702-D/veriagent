"""Unit tests for evaluation schemas, metrics, reports, and regression gating."""

import json
from pathlib import Path

import pytest
from eval.dataset import (
    DatasetValidationError,
    EvalClaim,
    RecordedRun,
    RecordedSource,
    load_claims,
)
from eval.metrics import (
    citation_validity,
    classification_accuracy,
    confusion_matrix,
    evaluate_runs,
    human_agreement,
    retrieval_precision,
    unsupported_claim_rate,
)
from eval.run_eval import regression_failures, render_markdown, write_corpus_comparison

from veriagent.schemas import Evidence, Finding, Stance, Verdict


def _evidence(
    evidence_id: str, *, verified: bool = True, stance: Stance = Stance.SUPPORTS
) -> Evidence:
    return Evidence(
        id=evidence_id,
        source_id="source-1",
        quote="A short, directly matched quotation.",
        stance=stance,
        quote_verified=verified,
    )


def _finding(*supporting: str) -> Finding:
    return Finding(
        subclaim_id="subclaim-1",
        supporting=list(supporting),
        verdict=Verdict.SUPPORTED,
        confidence=0.9,
    )


def test_load_claims_validates_jsonl_and_defaults_human_verdict(tmp_path: Path) -> None:
    dataset = tmp_path / "claims.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "case-1",
                "claim": "A valid claim.",
                "expected_verdict": "MIXED",
                "expected_domains": ["WWW.Example.org"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    claims = load_claims(dataset)

    assert claims[0].human_verdict == Verdict.MIXED
    assert claims[0].expected_domains == ["example.org"]


@pytest.mark.parametrize(
    "body, message",
    [
        ("{not-json}\n", "invalid JSON"),
        (
            '{"id":"duplicate","claim":"First claim","expected_verdict":"SUPPORTED"}\n'
            '{"id":"duplicate","claim":"Second claim","expected_verdict":"REFUTED"}\n',
            "duplicate claim id",
        ),
    ],
)
def test_load_claims_reports_line_aware_errors(tmp_path: Path, body: str, message: str) -> None:
    dataset = tmp_path / "claims.jsonl"
    dataset.write_text(body, encoding="utf-8")

    with pytest.raises(DatasetValidationError, match=message):
        load_claims(dataset)


def test_retrieval_precision_matches_exact_urls_and_domains() -> None:
    sources = [
        RecordedSource(url="https://EXAMPLE.org/study/", domain="www.example.org"),
        RecordedSource(url="https://trusted.test/other", domain="trusted.test"),
        RecordedSource(url="https://noise.test/page", domain="noise.test"),
    ]

    score = retrieval_precision(
        sources,
        expected_urls=["https://example.org/study"],
        expected_domains=["trusted.test"],
    )

    assert score == pytest.approx(2 / 3)
    assert retrieval_precision([], [], []) == 0.0


def test_citation_validity_counts_only_verified_quotes() -> None:
    evidence = [_evidence("verified"), _evidence("unverified", verified=False)]

    assert citation_validity(evidence) == 0.5
    assert citation_validity([]) == 0.0


def test_classification_accuracy_and_confusion_matrix() -> None:
    predicted = [Verdict.SUPPORTED, Verdict.MIXED, Verdict.CONDITIONAL]
    expected = [Verdict.SUPPORTED, Verdict.CONDITIONAL, Verdict.CONDITIONAL]

    assert classification_accuracy(predicted, expected) == pytest.approx(2 / 3)
    matrix = confusion_matrix(predicted, expected)
    assert matrix["SUPPORTED"]["SUPPORTED"] == 1
    assert matrix["CONDITIONAL"]["MIXED"] == 1
    assert matrix["CONDITIONAL"]["CONDITIONAL"] == 1


def test_unsupported_claim_rate_requires_verified_supporting_quote() -> None:
    evidence = [
        _evidence("good"),
        _evidence("unverified", verified=False),
        _evidence("contradiction", stance=Stance.CONTRADICTS),
    ]
    findings = [_finding("good"), _finding("unverified"), _finding("contradiction")]

    assert unsupported_claim_rate(findings, evidence) == pytest.approx(2 / 3)
    assert unsupported_claim_rate([], evidence) == 0.0


def test_human_agreement_reports_adjacent_separately() -> None:
    predicted = [Verdict.SUPPORTED, Verdict.MIXED, Verdict.REFUTED]
    human = [Verdict.SUPPORTED, Verdict.CONDITIONAL, Verdict.INSUFFICIENT]

    exact, adjacent = human_agreement(predicted, human)

    assert exact == pytest.approx(1 / 3)
    assert adjacent == pytest.approx(1 / 3)


def test_evaluate_runs_micro_aggregates_and_renders_report() -> None:
    claim = EvalClaim(
        id="case-1",
        claim="A valid evaluation claim.",
        expected_verdict=Verdict.SUPPORTED,
        expected_domains=["example.org"],
    )
    run = RecordedRun(
        case_id="case-1",
        sources=[RecordedSource(url="https://example.org/paper", domain="example.org")],
        evidence=[_evidence("good")],
        findings=[_finding("good")],
        verdict=Verdict.SUPPORTED,
    )

    report = evaluate_runs([claim], [run])
    markdown = render_markdown(report)

    assert report.retrieval_precision == 1.0
    assert report.unsupported_claim_rate == 0.0
    assert "## Confusion matrix" in markdown
    assert "| case-1 | SUPPORTED | SUPPORTED |" in markdown


def test_regression_gate_handles_higher_and_lower_is_better_metrics() -> None:
    baseline = {
        "retrieval_precision": 0.90,
        "citation_validity": 0.90,
        "classification_accuracy": 0.90,
        "unsupported_claim_rate": 0.10,
        "human_agreement": 0.90,
    }
    current = {
        "retrieval_precision": 0.79,
        "citation_validity": 0.89,
        "classification_accuracy": 0.90,
        "unsupported_claim_rate": 0.21,
        "human_agreement": 0.90,
    }

    failures = regression_failures(current, baseline, tolerance=0.05)

    assert any("retrieval_precision" in failure for failure in failures)
    assert any("unsupported_claim_rate" in failure for failure in failures)
    assert not any("citation_validity" in failure for failure in failures)


def test_corpus_ablation_writes_metric_deltas(tmp_path: Path) -> None:
    claim = EvalClaim(
        id="case-1",
        claim="A curated source supports this claim.",
        expected_verdict=Verdict.SUPPORTED,
        expected_domains=["curated"],
    )
    without_run = RecordedRun(case_id="case-1", verdict=Verdict.INSUFFICIENT)
    with_run = RecordedRun(
        case_id="case-1",
        sources=[RecordedSource(url="corpus://doc/chunk", domain="curated")],
        evidence=[_evidence("good")],
        findings=[_finding("good")],
        verdict=Verdict.SUPPORTED,
    )
    without_report = evaluate_runs([claim], [without_run], mode="without-corpus")
    with_report = evaluate_runs([claim], [with_run], mode="with-corpus")

    json_path, markdown_path = write_corpus_comparison(without_report, with_report, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["delta_with_minus_without"]["retrieval_precision"] == 1.0
    assert "| Retrieval Precision | 0.000 | 1.000 | +1.000 |" in markdown_path.read_text(
        encoding="utf-8"
    )
