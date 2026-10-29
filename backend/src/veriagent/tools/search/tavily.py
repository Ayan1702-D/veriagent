"""Optional Tavily search provider enabled when TAVILY_API_KEY is present."""

import logging

import httpx

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.tools.search.base import SearchResult

logger = logging.getLogger(__name__)
_TAVILY_API = "https://api.tavily.com/search"


class TavilySearchProvider:
    """Queries Tavily AI search API."""

    name: str = "tavily"

    def __init__(
        self,
        api_key: str,
        timeout: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize Tavily provider with API key."""
        self.api_key = api_key
        self.timeout = timeout
        self._client = client

    async def search(
        self,
        query: str,
        limit: int = 5,
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> list[SearchResult]:
        """Execute Tavily query or return empty list if disabled/error."""
        if not self.api_key:
            return []

        if budget is not None:
            budget.consume("searches", 1)

        results: list[SearchResult] = []
        payload = {"api_key": self.api_key, "query": query, "max_results": max(1, limit)}

        try:
            if self._client is not None:
                resp = await self._client.post(_TAVILY_API, json=payload, timeout=self.timeout)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    resp = await c.post(_TAVILY_API, json=payload)

            if resp.status_code == 200:
                for item in resp.json().get("results", []):
                    title = item.get("title") or ""
                    url = item.get("url") or ""
                    snippet = item.get("content") or ""
                    if title and url:
                        results.append(
                            SearchResult(
                                title=title,
                                url=url,
                                snippet=snippet,
                                provider=self.name,
                            )
                        )
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)

        if recorder is not None:
            recorder.record(
                node="researcher",
                type="search_completed",
                payload={"provider": self.name, "query": query, "hit_count": len(results)},
            )
        return results
