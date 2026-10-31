"""Core Pydantic v2 data models and enums for VeriAgent."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(UTC)


def _new_id() -> str:
    """Return a random UUID4 hex string."""
    return uuid4().hex


class Verdict(StrEnum):
    """Calibrated verification verdict taxonomy."""

    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    MIXED = "MIXED"
    CONDITIONAL = "CONDITIONAL"
    INSUFFICIENT = "INSUFFICIENT"


class Stance(StrEnum):
    """Relationship between an extracted quote and a claim/subclaim."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class SourceType(StrEnum):
    """Classification of an information source."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    NEWS = "news"
    BLOG = "blog"
    CURATED = "curated"


class Claim(BaseModel):
    """User-submitted claim decomposed into qualifiers and atomic subclaims."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    text: str = Field(min_length=3, max_length=2000)
    qualifiers: list[str] = Field(default_factory=list)
    atomic_subclaims: list[str] = Field(default_factory=list)


class SubQuestion(BaseModel):
    """Investigative question targeting a specific aspect or boundary of a claim."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    claim_id: str = Field(min_length=1)
    question: str = Field(min_length=3, max_length=1000)
    search_queries: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """Fetched web document or primary source with snapshot provenance."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=500)
    domain: str = Field(min_length=1, max_length=255)
    fetched_at: datetime = Field(default_factory=_utc_now)
    snapshot_hash: str = Field(min_length=1, max_length=128)
    rank_score: float = Field(default=0.0, ge=0.0, le=1.0)
    source_type: SourceType = Field(default=SourceType.SECONDARY)


class Evidence(BaseModel):
    """Extracted verbatim quote tied to a stored source snapshot."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=4000)
    date: str | None = Field(default=None, max_length=64)
    stance: Stance = Field(default=Stance.NEUTRAL)
    quote_verified: bool = Field(default=False)
    context_conditions: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """Synthesized finding for an atomic subclaim."""

    model_config = ConfigDict(extra="forbid")

    subclaim_id: str = Field(min_length=1)
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdict: Verdict = Field(default=Verdict.INSUFFICIENT)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RunBudget(BaseModel):
    """Hard resource limits for a single verification run."""

    model_config = ConfigDict(extra="forbid")

    max_llm_tokens: int = Field(default=12000, ge=1)
    max_searches: int = Field(default=6, ge=1)
    max_fetches: int = Field(default=10, ge=1)
    max_loops: int = Field(default=2, ge=0)
    max_seconds: float = Field(default=60.0, gt=0.0)


class AuditEvent(BaseModel):
    """Ordered audit trail event emitted during a run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    seq: int = Field(ge=1)
    node: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    tokens: int = Field(default=0, ge=0)
    ts: datetime = Field(default_factory=_utc_now)


class Report(BaseModel):
    """Final verification report returned to the caller."""

    model_config = ConfigDict(extra="forbid")

    claim: Claim
    findings: list[Finding] = Field(default_factory=list)
    verdict: Verdict = Field(default=Verdict.INSUFFICIENT)
    limitations: list[str] = Field(default_factory=list)
    citations: list[Source] = Field(default_factory=list)
