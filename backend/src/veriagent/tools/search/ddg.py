"""Keyless web search provider using the maintained DDGS metasearch package."""

import asyncio
import logging

from ddgs import DDGS

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.tools.search.base import SearchResult

logger = logging.getLogger(__name__)


class DuckDuckGoSearchProvider:
    """Performs keyless web searches through DDGS metasearch."""

    name: str = "ddgs"

    def __init__(self, timeout: float = 8.0) -> None:
        """Initialize provider with timeout."""
        self.timeout = timeout

    async def search(
        self,
        query: str,
        limit: int = 5,
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> list[SearchResult]:
        """Execute DuckDuckGo text search, returning [] on error."""
        if budget is not None:
            budget.consume("searches", 1)

        results: list[SearchResult] = []
        try:

            def get_hits() -> list[dict[str, str]]:
                with DDGS(timeout=int(self.timeout)) as search:
                    return search.text(query, max_results=max(1, limit))

            raw_hits = await asyncio.to_thread(get_hits)
            for hit in raw_hits:
                url = str(hit.get("href") or hit.get("url") or "")
                title = str(hit.get("title") or "")
                snippet = str(hit.get("body") or hit.get("snippet") or "")
                if url and title:
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
                "DuckDuckGo search failed for query=%r: %s",
                query,
                exc,
                extra={"query": query},
            )
            if recorder is not None:
                recorder.record(
                    node="researcher",
                    type="search_failed",
                    payload={"provider": self.name, "query": query, "reason": type(exc).__name__},
                )
            return []

        if recorder is not None:
            recorder.record(
                node="researcher",
                type="search_completed",
                payload={"provider": self.name, "query": query, "hit_count": len(results)},
            )
        return results
