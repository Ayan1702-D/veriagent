"""Pure metric calculations for VeriAgent evaluation runs."""

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from eval.dataset import EvalClaim, RecordedRun, RecordedSource
from veriagent.schemas import Evidence, Finding, Stance, Verdict

_VERDICTS = tuple(Verdict)
_ADJACENT_PAIRS = {
    frozenset((Verdict.MIXED, Verdict.CONDITIONAL)),
}


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _normalize_domain(value: str) -> str:
    candidate = value.strip().lower()
    if "://" in candidate:
        candidate = urlparse(candidate).hostname or ""
    return candidate.removeprefix("www.").rstrip(".")


def _normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    host = _normalize_domain(parsed.hostname or "")
    path = parsed.path.rstrip("/") or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{host}{path}{query}"


def source_is_relevant(
    source: RecordedSource,
    expected_urls: Sequence[str],
    expected_domains: Sequence[str],
) -> bool:
    """Return whether a retrieved source matches an expected URL or domain."""
    source_url = _normalize_url(source.url)
    source_domain = _normalize_domain(source.domain or source.url)
    urls = {_normalize_url(url) for url in expected_urls}
    domains = {_normalize_domain(domain) for domain in expected_domains}
    return source_url in urls or source_domain in domains


def retrieval_precision(
    sources: Sequence[RecordedSource],
    expected_urls: Sequence[str],
    expected_domains: Sequence[str],
) -> float:
    """Relevant retrieved sources divided by all retrieved sources."""
    relevant = sum(
        source_is_relevant(source, expected_urls, expected_domains) for source in sources
    )
    return _ratio(relevant, len(sources))


def citation_validity(evidence: Sequence[Evidence]) -> float:
    """Deterministically verified quotes divided by all extracted quotes."""
    return _ratio(sum(item.quote_verified for item in evidence), len(evidence))


def classification_accuracy(predicted: Sequence[Verdict], expected: Sequence[Verdict]) -> float:
    """Exact verdict matches divided by evaluated verdicts."""
    if len(predicted) != len(expected):
        raise ValueError("predicted and expected verdict lists must have equal length")
    return _ratio(
        sum(left == right for left, right in zip(predicted, expected, strict=True)), len(expected)
    )


def confusion_matrix(
    predicted: Sequence[Verdict], expected: Sequence[Verdict]
) -> dict[str, dict[str, int]]:
    """Build an expected-row, predicted-column matrix across all verdict labels."""
    if len(predicted) != len(expected):
        raise ValueError("predicted and expected verdict lists must have equal length")
    matrix = {actual.value: {candidate.value: 0 for candidate in _VERDICTS} for actual in _VERDICTS}
    for actual, candidate in zip(expected, predicted, strict=True):
        matrix[actual.value][candidate.value] += 1
    return matrix


def unsupported_claim_rate(findings: Sequence[Finding], evidence: Sequence[Evidence]) -> float:
    """Fraction of findings lacking a referenced, verified supporting quote."""
    verified_support_ids = {
        item.id for item in evidence if item.quote_verified and item.stance == Stance.SUPPORTS
    }
    unsupported = sum(
        not any(evidence_id in verified_support_ids for evidence_id in finding.supporting)
        for finding in findings
    )
    return _ratio(unsupported, len(findings))


def human_agreement(predicted: Sequence[Verdict], human: Sequence[Verdict]) -> tuple[float, float]:
    """Return exact agreement and non-exact adjacent agreement as separate rates."""
    if len(predicted) != len(human):
        raise ValueError("predicted and human verdict lists must have equal length")
    exact = 0
    adjacent = 0
    for candidate, reviewed in zip(predicted, human, strict=True):
        if candidate == reviewed:
            exact += 1
        elif frozenset((candidate, reviewed)) in _ADJACENT_PAIRS:
            adjacent += 1
    return _ratio(exact, len(human)), _ratio(adjacent, len(human))


class CaseMetrics(BaseModel):
    """Per-claim measurements included for diagnosis in reports."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    predicted_verdict: Verdict
    expected_verdict: Verdict
    human_verdict: Verdict
    retrieval_precision: float = Field(ge=0.0, le=1.0)
    citation_validity: float = Field(ge=0.0, le=1.0)
    unsupported_claim_rate: float = Field(ge=0.0, le=1.0)
    exact_match: bool
    adjacent_human_match: bool


class EvalReport(BaseModel):
    """Aggregate evaluation output serialized as JSON and Markdown."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    mode: str
    dataset_size: int = Field(ge=1)
    retrieval_precision: float = Field(ge=0.0, le=1.0)
    citation_validity: float = Field(ge=0.0, le=1.0)
    classification_accuracy: float = Field(ge=0.0, le=1.0)
    unsupported_claim_rate: float = Field(ge=0.0, le=1.0)
    human_agreement: float = Field(ge=0.0, le=1.0)
    adjacent_agreement: float = Field(ge=0.0, le=1.0)
    confusion_matrix: dict[str, dict[str, int]]
    verdict_distribution: dict[str, int]
    cases: list[CaseMetrics]


def evaluate_runs(
    claims: Sequence[EvalClaim], runs: Sequence[RecordedRun], mode: str = "replay"
) -> EvalReport:
    """Calculate micro-aggregated metrics and per-case diagnostic results."""
    run_by_id = {run.case_id: run for run in runs}
    if len(run_by_id) != len(runs):
        raise ValueError("recorded run case IDs must be unique")
    missing = [claim.id for claim in claims if claim.id not in run_by_id]
    extra = sorted(set(run_by_id) - {claim.id for claim in claims})
    if missing or extra:
        raise ValueError(f"dataset/result mismatch: missing={missing}, extra={extra}")

    retrieved_total = relevant_total = 0
    quote_total = verified_total = 0
    finding_total = unsupported_total = 0
    predicted: list[Verdict] = []
    expected: list[Verdict] = []
    human: list[Verdict] = []
    cases: list[CaseMetrics] = []

    for claim in claims:
        run = run_by_id[claim.id]
        relevant = sum(
            source_is_relevant(source, claim.expected_urls, claim.expected_domains)
            for source in run.sources
        )
        verified = sum(item.quote_verified for item in run.evidence)
        unsupported_rate = unsupported_claim_rate(run.findings, run.evidence)
        unsupported = round(unsupported_rate * len(run.findings))
        reviewed = claim.human_verdict or claim.expected_verdict
        adjacent = run.verdict != reviewed and frozenset((run.verdict, reviewed)) in _ADJACENT_PAIRS

        retrieved_total += len(run.sources)
        relevant_total += relevant
        quote_total += len(run.evidence)
        verified_total += verified
        finding_total += len(run.findings)
        unsupported_total += unsupported
        predicted.append(run.verdict)
        expected.append(claim.expected_verdict)
        human.append(reviewed)
        cases.append(
            CaseMetrics(
                case_id=claim.id,
                predicted_verdict=run.verdict,
                expected_verdict=claim.expected_verdict,
                human_verdict=reviewed,
                retrieval_precision=_ratio(relevant, len(run.sources)),
                citation_validity=_ratio(verified, len(run.evidence)),
                unsupported_claim_rate=unsupported_rate,
                exact_match=run.verdict == claim.expected_verdict,
                adjacent_human_match=adjacent,
            )
        )

    exact_agreement, adjacent_agreement = human_agreement(predicted, human)
    verdict_counts = Counter(item.value for item in predicted)
    return EvalReport(
        generated_at=datetime.now(UTC),
        mode=mode,
        dataset_size=len(claims),
        retrieval_precision=_ratio(relevant_total, retrieved_total),
        citation_validity=_ratio(verified_total, quote_total),
        classification_accuracy=classification_accuracy(predicted, expected),
        unsupported_claim_rate=_ratio(unsupported_total, finding_total),
        human_agreement=exact_agreement,
        adjacent_agreement=adjacent_agreement,
        confusion_matrix=confusion_matrix(predicted, expected),
        verdict_distribution={
            verdict.value: verdict_counts[verdict.value] for verdict in _VERDICTS
        },
        cases=cases,
    )
