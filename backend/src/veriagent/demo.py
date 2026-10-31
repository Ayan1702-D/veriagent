"""Pre-seeded, evidence-backed runs used by the free-tier demo fallback."""

from dataclasses import dataclass
from hashlib import sha256

from veriagent.audit.recorder import AuditRecorder
from veriagent.db.repo import DatabaseAuditSink, RunRepository
from veriagent.schemas import (
    Claim,
    Evidence,
    Finding,
    Report,
    RunBudget,
    Source,
    SourceType,
    Stance,
    Verdict,
)


@dataclass(frozen=True)
class DemoRun:
    """One immutable source run that can be copied through the replay API."""

    run_id: str
    claim: Claim
    source: Source
    snapshot: str
    evidence: list[Evidence]
    report: Report


def _make_demo(
    *,
    run_id: str,
    claim_text: str,
    source_id: str,
    source_url: str,
    source_title: str,
    source_domain: str,
    quote: str,
    verdict: Verdict,
    confidence: float,
    limitations: list[str],
    context: list[str],
    stance: Stance = Stance.SUPPORTS,
) -> DemoRun:
    snapshot = quote
    claim = Claim(id=f"claim-{run_id}", text=claim_text, atomic_subclaims=[claim_text])
    source = Source(
        id=source_id,
        url=source_url,
        title=source_title,
        domain=source_domain,
        snapshot_hash=sha256(snapshot.encode("utf-8")).hexdigest(),
        rank_score=0.95,
        source_type=SourceType.PRIMARY,
    )
    evidence_id = f"ev-{run_id}"
    evidence = Evidence(
        id=evidence_id,
        source_id=source.id,
        quote=quote,
        stance=stance,
        quote_verified=True,
        context_conditions=context,
    )
    finding = Finding(
        subclaim_id=claim_text,
        supporting=[evidence_id] if stance == Stance.SUPPORTS else [],
        contradicting=[evidence_id] if stance == Stance.CONTRADICTS else [],
        gaps=limitations,
        verdict=verdict,
        confidence=confidence,
    )
    report = Report(
        claim=claim,
        findings=[finding],
        verdict=verdict,
        limitations=limitations,
        citations=[source],
    )
    return DemoRun(run_id, claim, source, snapshot, [evidence], report)


DEMO_RUNS: tuple[DemoRun, ...] = (
    _make_demo(
        run_id="demo-ev-grid",
        claim_text=(
            "Electric vehicles always produce fewer lifetime emissions, regardless of grid mix."
        ),
        source_id="iea-ev-outlook-2024",
        source_url=(
            "https://www.iea.org/reports/global-ev-outlook-2024/outlook-for-emissions-reductions"
        ),
        source_title="Global EV Outlook 2024: Outlook for emissions reductions",
        source_domain="iea.org",
        quote=(
            "These emissions savings increase by around 5 percentage points in the APS, "
            "as the grid decarbonises more quickly than in the STEPS."
        ),
        verdict=Verdict.CONDITIONAL,
        confidence=0.91,
        limitations=[
            "Lifecycle results vary by vehicle, battery, lifetime mileage, and electricity mix."
        ],
        context=["Global medium-size vehicles", "IEA STEPS and APS scenarios"],
    ),
    _make_demo(
        run_id="demo-remote-productivity",
        claim_text="Remote work makes software teams more productive than office work.",
        source_id="msr-triple-peak",
        source_url=(
            "https://www.microsoft.com/en-us/research/publication/"
            "triple-peak-day-work-rhythms-of-software-developers-in-hybrid-work/"
        ),
        source_title="Triple Peak Day: Work Rhythms of Software Developers in Hybrid Work",
        source_domain="microsoft.com",
        quote=(
            "This third peak was associated with higher perceived productivity during remote "
            "days but increased stress during onsite and hybrid days"
        ),
        verdict=Verdict.MIXED,
        confidence=0.82,
        limitations=[
            "The study measured 65 developers and perceived productivity; it does not establish "
            "that every remote team outperforms every office team."
        ],
        context=["Month-long observational study", "65 software developers"],
    ),
    _make_demo(
        run_id="demo-coffee-sleep",
        claim_text="Drinking coffee after 2 PM always disrupts nighttime sleep.",
        source_id="pubmed-caffeine-timing",
        source_url="https://pubmed.ncbi.nlm.nih.gov/39377163/",
        source_title="Dose and timing effects of caffeine on subsequent sleep",
        source_domain="pubmed.ncbi.nlm.nih.gov",
        quote=(
            "No significant effect on objective or subjective sleep occurred with the 100 mg "
            "dose of caffeine compared with the placebo"
        ),
        verdict=Verdict.REFUTED,
        confidence=0.9,
        limitations=[
            "Sleep effects depend on dose, bedtime, habitual intake, and individual sensitivity."
        ],
        context=["100 mg dose", "Randomized crossover trial of 23 adult males"],
        stance=Stance.CONTRADICTS,
    ),
)

_DEMO_BY_CLAIM = {" ".join(item.claim.text.split()).casefold(): item.run_id for item in DEMO_RUNS}


def demo_run_id_for_claim(claim: str) -> str | None:
    """Return the seeded source ID when a submitted claim matches a demo claim."""
    return _DEMO_BY_CLAIM.get(" ".join(claim.split()).casefold())


def seed_demo_runs(repository: RunRepository, budget: RunBudget) -> None:
    """Idempotently create completed source runs for offline replay."""
    zero_usage: dict[str, float | int] = {
        "tokens": 0,
        "searches": 0,
        "fetches": 0,
        "loops": 0,
        "seconds": 0.0,
    }
    for demo in DEMO_RUNS:
        row = repository.get_run(demo.run_id)
        if row is None:
            repository.create_run(demo.run_id, demo.claim, budget)
        if repository.get_report(demo.run_id) is None:
            repository.save_artifacts(
                demo.run_id,
                [demo.source],
                {demo.source.id: demo.snapshot},
                demo.evidence,
                demo.report,
            )
        repository.set_status(demo.run_id, "completed", budget_usage=zero_usage)
        if not repository.list_audit_events(demo.run_id):
            recorder = AuditRecorder(demo.run_id, sink=DatabaseAuditSink(repository))
            recorder.record(
                node="system",
                type="demo_seeded",
                payload={"offline_replay_ready": True},
            )
