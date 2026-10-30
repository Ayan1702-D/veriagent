"""SQLAlchemy persistence models for runs and their verification artifacts."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative model base."""


class RunRow(Base):
    """One verification or replay run."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    claim_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    budget_usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    replay_of: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("runs.id"), nullable=True, index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SourceRow(Base):
    """Fetched source associated with a run."""

    __tablename__ = "sources"

    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(500), default="")
    domain: Mapped[str] = mapped_column(String(255))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot_hash: Mapped[str] = mapped_column(String(128))
    snapshot_text: Mapped[str] = mapped_column(Text, default="")
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_type: Mapped[str] = mapped_column(String(20))


class EvidenceRow(Base):
    """Extracted evidence associated with a run."""

    __tablename__ = "evidence"

    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(32), index=True)
    quote: Mapped[str] = mapped_column(Text)
    date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stance: Mapped[str] = mapped_column(String(20))
    quote_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    context_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)


class AuditEventRow(Base):
    """Strictly ordered audit event for a run."""

    __tablename__ = "audit_events"

    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    node: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReportRow(Base):
    """Final structured report for a run."""

    __tablename__ = "reports"

    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
