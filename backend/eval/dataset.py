"""Validated evaluation dataset and recorded-run artifact schemas."""

import json
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from veriagent.schemas import Evidence, Finding, RunBudget, Verdict


class DatasetValidationError(ValueError):
    """Raised when an evaluation JSONL row is malformed or duplicated."""


class EvalClaim(BaseModel):
    """One human-reviewed claim and its retrieval/verdict expectations."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    claim: str = Field(min_length=3, max_length=2000)
    expected_verdict: Verdict
    human_verdict: Verdict | None = None
    expected_urls: list[str] = Field(default_factory=list)
    expected_domains: list[str] = Field(default_factory=list)
    budget: RunBudget = Field(default_factory=RunBudget)
    notes: str = Field(default="", max_length=2000)

    @field_validator("claim")
    @classmethod
    def normalize_claim(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("claim must contain at least 3 non-whitespace characters")
        return normalized

    @field_validator("expected_urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            parsed = urlparse(value.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"expected URL must be absolute HTTP(S): {value!r}")
            normalized.append(value.strip())
        return list(dict.fromkeys(normalized))

    @field_validator("expected_domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            domain = value.strip().lower().removeprefix("www.").rstrip(".")
            if not domain or "/" in domain or "://" in domain:
                raise ValueError(f"expected domain must be a hostname: {value!r}")
            normalized.append(domain)
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def default_human_verdict(self) -> "EvalClaim":
        if self.human_verdict is None:
            self.human_verdict = self.expected_verdict
        return self


class RecordedSource(BaseModel):
    """Minimal retrieved-source fields required by evaluation metrics."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    domain: str = Field(min_length=1, max_length=255)


class RecordedRun(BaseModel):
    """Compact graph output used for deterministic offline replay."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    sources: list[RecordedSource] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    verdict: Verdict


def load_claims(path: Path) -> list[EvalClaim]:
    """Load and validate a JSONL dataset, reporting precise source line failures."""
    if not path.is_file():
        raise DatasetValidationError(f"Evaluation dataset not found: {path}")

    claims: list[EvalClaim] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        try:
            claim = EvalClaim.model_validate(raw)
        except ValidationError as exc:
            raise DatasetValidationError(f"{path}:{line_number}: {exc}") from exc
        if claim.id in seen_ids:
            raise DatasetValidationError(f"{path}:{line_number}: duplicate claim id {claim.id!r}")
        seen_ids.add(claim.id)
        claims.append(claim)

    if not claims:
        raise DatasetValidationError(f"Evaluation dataset contains no claims: {path}")
    return claims


def load_recorded_run(path: Path, expected_case_id: str | None = None) -> RecordedRun:
    """Load a previously recorded graph result for offline scoring."""
    try:
        run = RecordedRun.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetValidationError(f"Replay artifact not found: {path}") from exc
    except ValidationError as exc:
        raise DatasetValidationError(f"Invalid replay artifact {path}: {exc}") from exc
    if expected_case_id is not None and run.case_id != expected_case_id:
        raise DatasetValidationError(
            f"Replay artifact {path} belongs to {run.case_id!r}, expected {expected_case_id!r}"
        )
    return run


def write_recorded_run(path: Path, run: RecordedRun) -> None:
    """Persist a graph result for future offline replay."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
