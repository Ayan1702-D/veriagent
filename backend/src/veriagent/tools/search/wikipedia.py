"""Wikipedia API search provider using the MediaWiki action API."""

import logging

import httpx

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.tools.search.base import SearchResult

logger = logging.getLogger(__name__)
_WIKI_API = "https://en.wikipedia.org/w/api.php"


class WikipediaSearchProvider:
    """Performs encyclopedia topic search via Wikipedia Action API."""

    name: str = "wikipedia"

    def __init__(self, timeout: float = 6.0, client: httpx.AsyncClient | None = None) -> None:
        """Initialize Wikipedia provider."""
        self.timeout = timeout
        self._client = client

    async def search(
        self,
        query: str,
        limit: int = 5,
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> list[SearchResult]:
        """Query Wikipedia API and return up to `limit` SearchResult items."""
        if budget is not None:
            budget.consume("searches", 1)

        results: list[SearchResult] = []
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": max(1, limit),
        }
        headers = {"User-Agent": "VeriAgent/0.1.0 (academic-research)"}

        try:
            if self._client is not None:
                resp = await self._client.get(
                    _WIKI_API, params=params, headers=headers, timeout=self.timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    resp = await c.get(_WIKI_API, params=params, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("query", {}).get("search", []):
                    title = item.get("title", "")
                    page_id = item.get("pageid")
                    url = f"https://en.wikipedia.org/?curid={page_id}"
                    snippet = (
                        item.get("snippet", "")
                        .replace('<span class="searchmatch">', "")
                        .replace("</span>", "")
                    )
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
            logger.warning(
                "Wikipedia search failed for query=%r: %s",
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
