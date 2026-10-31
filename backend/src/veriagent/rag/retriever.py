"""Curated-corpus retrieval exposed through the standard search provider contract."""

import asyncio
from typing import Any
from urllib.parse import quote

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.rag.ingest import CorpusIndex
from veriagent.schemas import SourceType
from veriagent.tools.search.base import SearchResult


class CorpusSearchProvider:
    """Retrieve top-k Chroma chunks as normalized search results."""

    name = "curated_corpus"

    def __init__(self, index: CorpusIndex, top_k: int = 3) -> None:
        self.index = index
        self.top_k = top_k

    @staticmethod
    def _first_batch(result: dict[str, Any], key: str) -> list[Any]:
        value = result.get(key) or []
        if not isinstance(value, list) or not value:
            return []
        first = value[0]
        return first if isinstance(first, list) else []

    def retrieve(self, query: str, limit: int | None = None) -> list[SearchResult]:
        """Return ranked chunks with stored text attached for snapshot verification."""
        result = self.index.query(query, limit or self.top_k)
        documents = self._first_batch(result, "documents")
        metadata = self._first_batch(result, "metadatas")
        distances = self._first_batch(result, "distances")
        hits: list[SearchResult] = []
        for index, document in enumerate(documents):
            if not isinstance(document, str) or not document.strip():
                continue
            item_metadata = metadata[index] if index < len(metadata) else {}
            if not isinstance(item_metadata, dict):
                item_metadata = {}
            path = str(item_metadata.get("path", "document"))
            page = int(item_metadata.get("page", 1))
            chunk_index = int(item_metadata.get("chunk_index", index))
            title = str(item_metadata.get("title") or path)
            document_id = str(item_metadata.get("document_id", "unknown"))
            distance = float(distances[index]) if index < len(distances) else 0.5
            score = max(0.0, min(1.0, 1.0 - distance))
            hits.append(
                SearchResult(
                    title=f"{title} · page {page}",
                    url=(
                        f"corpus://{quote(document_id, safe='')}/{quote(path, safe='/')}"
                        f"?page={page}&chunk={chunk_index}"
                    ),
                    snippet=document[:500],
                    provider=self.name,
                    source_type=SourceType.CURATED,
                    snapshot_text=document,
                    rank_score=score,
                )
            )
        return hits

    async def search(
        self,
        query: str,
        limit: int = 5,
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> list[SearchResult]:
        """Search locally without blocking the API event loop."""
        if budget is not None:
            budget.consume("searches", 1)
        hits = await asyncio.to_thread(self.retrieve, query, min(limit, self.top_k))
        if recorder is not None:
            recorder.record(
                node="researcher",
                type="search_completed",
                payload={"provider": self.name, "query": query, "hit_count": len(hits)},
            )
        return hits
