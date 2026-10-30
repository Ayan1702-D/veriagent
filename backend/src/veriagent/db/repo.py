"""Repository operations and the database-backed audit sink."""

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from veriagent.audit.recorder import AuditSink
from veriagent.db.models import (
    AuditEventRow,
    EvidenceRow,
    ReportRow,
    RunRow,
    SourceRow,
)
from veriagent.schemas import AuditEvent, Claim, Evidence, Report, RunBudget, Source


class RunRepository:
    """Short-lived-session repository for run persistence."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_run(
        self,
        run_id: str,
        claim: Claim,
        budget: RunBudget,
        replay_of: str | None = None,
    ) -> None:
        """Insert a queued run."""
        with self._session_factory.begin() as session:
            session.add(
                RunRow(
                    id=run_id,
                    status="queued",
                    claim_json=claim.model_dump(mode="json"),
                    budget_json=budget.model_dump(mode="json"),
                    budget_usage_json={},
                    replay_of=replay_of,
                )
            )

    def get_run(self, run_id: str) -> RunRow | None:
        """Return a detached run row, if present."""
        with self._session_factory() as session:
            return session.get(RunRow, run_id)

    def set_status(
        self,
        run_id: str,
        status: str,
        *,
        error: str | None = None,
        budget_usage: Mapping[str, float | int] | None = None,
    ) -> None:
        """Update lifecycle state and final budget usage."""
        with self._session_factory.begin() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            row.status = status
            row.error = error
            row.updated_at = datetime.now(UTC)
            if budget_usage is not None:
                row.budget_usage_json = dict(budget_usage)

    def save_artifacts(
        self,
        run_id: str,
        sources: list[Source],
        snapshots: Mapping[str, str],
        evidence: list[Evidence],
        report: Report,
    ) -> None:
        """Persist the final graph artifacts atomically."""
        with self._session_factory.begin() as session:
            for source in sources:
                session.merge(
                    SourceRow(
                        run_id=run_id,
                        id=source.id,
                        url=source.url,
                        title=source.title,
                        domain=source.domain,
                        fetched_at=source.fetched_at,
                        snapshot_hash=source.snapshot_hash,
                        snapshot_text=snapshots.get(source.id, ""),
                        rank_score=source.rank_score,
                        source_type=source.source_type.value,
                    )
                )
            for item in evidence:
                session.merge(
                    EvidenceRow(
                        run_id=run_id,
                        id=item.id,
                        source_id=item.source_id,
                        quote=item.quote,
                        date=item.date,
                        stance=item.stance.value,
                        quote_verified=item.quote_verified,
                        context_conditions=item.context_conditions,
                    )
                )
            session.merge(
                ReportRow(run_id=run_id, report_json=report.model_dump(mode="json"))
            )

    def get_report(self, run_id: str) -> Report | None:
        """Load a final report."""
        with self._session_factory() as session:
            row = session.get(ReportRow, run_id)
            return Report.model_validate(row.report_json) if row is not None else None

    def get_sources(self, run_id: str) -> tuple[list[Source], dict[str, str]]:
        """Load persisted sources and snapshots."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(SourceRow).where(SourceRow.run_id == run_id).order_by(SourceRow.id)
            ).all()
        sources = [
            Source.model_validate(
                {
                    "id": row.id,
                    "url": row.url,
                    "title": row.title,
                    "domain": row.domain,
                    "fetched_at": row.fetched_at,
                    "snapshot_hash": row.snapshot_hash,
                    "rank_score": row.rank_score,
                    "source_type": row.source_type,
                }
            )
            for row in rows
        ]
        return sources, {row.id: row.snapshot_text for row in rows}

    def get_evidence(self, run_id: str) -> list[Evidence]:
        """Load persisted evidence."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(EvidenceRow).where(EvidenceRow.run_id == run_id).order_by(EvidenceRow.id)
            ).all()
        return [
            Evidence.model_validate(
                {
                    "id": row.id,
                    "source_id": row.source_id,
                    "quote": row.quote,
                    "date": row.date,
                    "stance": row.stance,
                    "quote_verified": row.quote_verified,
                    "context_conditions": row.context_conditions,
                }
            )
            for row in rows
        ]

    def add_audit_event(self, event: AuditEvent) -> None:
        """Persist one ordered event."""
        with self._session_factory.begin() as session:
            session.add(
                AuditEventRow(
                    run_id=event.run_id,
                    seq=event.seq,
                    node=event.node,
                    type=event.type,
                    payload=event.payload,
                    tokens=event.tokens,
                    ts=event.ts,
                )
            )

    def list_audit_events(self, run_id: str, after_seq: int = 0) -> list[AuditEvent]:
        """Return audit events in sequence order."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.run_id == run_id, AuditEventRow.seq > after_seq)
                .order_by(AuditEventRow.seq)
            ).all()
        return [
            AuditEvent(
                run_id=row.run_id,
                seq=row.seq,
                node=row.node,
                type=row.type,
                payload=row.payload,
                tokens=row.tokens,
                ts=row.ts,
            )
            for row in rows
        ]


class DatabaseAuditSink(AuditSink):
    """AuditRecorder sink that commits every event to the database."""

    def __init__(self, repository: RunRepository) -> None:
        self._repository = repository

    def emit(self, event: AuditEvent) -> None:
        """Persist a newly recorded event."""
        self._repository.add_audit_event(event)
