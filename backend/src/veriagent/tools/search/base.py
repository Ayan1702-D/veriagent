"""Base schemas and protocol for search providers."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor


class SearchResult(BaseModel):
    """Normalized search result returned by any provider."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2048)
    snippet: str = Field(default="", max_length=5000)
    provider: str = Field(min_length=1, max_length=50)


@runtime_checkable
class SearchProvider(Protocol):
    """Interface implemented by all search tools."""

    name: str

    async def search(
        self,
        query: str,
        limit: int = 5,
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> list[SearchResult]:
        """Search query and return normalized results, tracking budget and audit events."""
