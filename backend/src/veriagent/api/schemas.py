"""HTTP request and response schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from veriagent.schemas import AuditEvent, Report


class BudgetRequest(BaseModel):
    """Optional client budget overrides, capped by server settings."""

    model_config = ConfigDict(extra="forbid")

    max_llm_tokens: int | None = Field(default=None, ge=1)
    max_searches: int | None = Field(default=None, ge=1)
    max_fetches: int | None = Field(default=None, ge=1)
    max_loops: int | None = Field(default=None, ge=0)
    max_seconds: float | None = Field(default=None, gt=0.0)


class CreateRunRequest(BaseModel):
    """New claim verification request."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=3, max_length=2000)
    budget: BudgetRequest | None = None

    @field_validator("claim")
    @classmethod
    def normalize_claim(cls, value: str) -> str:
        """Reject whitespace-only claims after normalization."""
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("claim must contain at least 3 non-whitespace characters")
        return normalized


class RunAcceptedResponse(BaseModel):
    """Accepted background run identifier."""

    run_id: str
    status: Literal["queued"] = "queued"


class RunResponse(BaseModel):
    """Current run state and optional final report."""

    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    claim: dict[str, Any]
    budget: dict[str, Any]
    budget_usage: dict[str, Any]
    replay_of: str | None
    report: Report | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class AuditResponse(BaseModel):
    """Complete ordered audit trail."""

    run_id: str
    events: list[AuditEvent]
