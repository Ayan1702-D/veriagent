"""OpenAlex scientific paper search provider."""

import logging

import httpx

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.tools.search.base import SearchResult

logger = logging.getLogger(__name__)
_OPENALEX_WORKS_API = "https://api.openalex.org/works"


class OpenAlexSearchProvider:
    """Queries peer-reviewed scientific literature via OpenAlex API."""

    name: str = "openalex"

    def __init__(
        self,
        mailto: str = "",
        timeout: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize OpenAlex provider with mailto header for the polite pool."""
        self.mailto = mailto
        self.timeout = timeout
        self._client = client

    async def search(
        self,
        query: str,
        limit: int = 5,
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> list[SearchResult]:
        """Search works by title/abstract text in OpenAlex."""
        if budget is not None:
            budget.consume("searches", 1)

        results: list[SearchResult] = []
        params: dict[str, str | int] = {
            "search": query,
            "per_page": max(1, limit),
        }
        headers = {"User-Agent": "VeriAgent/0.1.0"}
        if self.mailto:
            headers["User-Agent"] = f"VeriAgent/0.1.0 (mailto:{self.mailto})"

        try:
            if self._client is not None:
                resp = await self._client.get(
                    _OPENALEX_WORKS_API, params=params, headers=headers, timeout=self.timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    resp = await c.get(_OPENALEX_WORKS_API, params=params, headers=headers)

            if resp.status_code == 200:
                for work in resp.json().get("results", []):
                    title = work.get("title") or ""
                    doi = work.get("doi") or work.get("id") or ""
                    landing = work.get("primary_location", {}).get("landing_page_url") or doi
                    snippet_parts = []
                    if work.get("publication_year"):
                        snippet_parts.append(f"Year: {work['publication_year']}")
                    if work.get("cited_by_count") is not None:
                        snippet_parts.append(f"Citations: {work['cited_by_count']}")
                    if title and landing:
                        results.append(
                            SearchResult(
                                title=title,
                                url=landing,
                                snippet=" | ".join(snippet_parts),
                                provider=self.name,
                            )
                        )
        except Exception as exc:
            logger.warning(
                "OpenAlex search failed for query=%r: %s",
                query,
                exc,
                extra={"query": query},
            )

        if recorder is not None:
            recorder.record(
                node="researcher",
                type="search_completed",
                payload={"provider": self.name, "query": query, "hit_count": len(results)},
            )
        return results
