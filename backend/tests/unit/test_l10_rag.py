"""Curated corpus ingestion, retrieval, graph integration, and API tests."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import chromadb
import pytest
from fastapi.testclient import TestClient

from veriagent.config import Settings
from veriagent.core.budget import BudgetGovernor
from veriagent.graph.nodes.extractor import run_extractor_node
from veriagent.graph.nodes.researcher import run_researcher_node
from veriagent.llm.fake import FakeLLM
from veriagent.main import create_app
from veriagent.rag.ingest import (
    CorpusIndex,
    IngestResult,
    build_chunks,
    chunk_text,
    load_document,
)
from veriagent.rag.retriever import CorpusSearchProvider
from veriagent.schemas import Claim, RunBudget, SourceType, SubQuestion


class FakeEmbedder:
    """Small deterministic embedding model that avoids network/model downloads."""

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.lower()
        return [
            1.0 if "battery" in lowered else 0.0,
            1.0 if "coffee" in lowered else 0.0,
            0.1,
        ]

    def passage_embed(self, documents: list[str]) -> Iterable[list[float]]:
        return [self._vector(document) for document in documents]

    def query_embed(self, query: str) -> Iterable[list[float]]:
        return [self._vector(query)]


def test_chunk_text_has_overlap_and_validates_bounds() -> None:
    text = " ".join(f"word-{index}" for index in range(80))
    chunks = list(chunk_text(text, chunk_size=120, overlap=25))

    assert len(chunks) > 2
    assert any(word in chunks[1] for word in chunks[0].split()[-3:])
    assert all(len(chunk) <= 120 for chunk in chunks)
    with pytest.raises(ValueError, match="smaller than chunk_size"):
        list(chunk_text(text, chunk_size=100, overlap=100))


def test_load_and_build_text_chunks_with_metadata(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    document = corpus_dir / "research.md"
    document.write_text("Battery evidence " * 100, encoding="utf-8")

    pages = load_document(document)
    chunks, page_count = build_chunks(
        document,
        source_root=corpus_dir,
        title="Battery Research",
        chunk_size=200,
        overlap=40,
    )

    assert pages[0].page == 1
    assert page_count == 1
    assert len(chunks) > 1
    assert chunks[0].title == "Battery Research"
    assert chunks[0].path == "research.md"
    assert chunks[0].page == 1
    assert chunks[0].id.startswith(chunks[0].document_id)


def test_pdf_loader_preserves_page_numbers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = tmp_path / "paper.pdf"
    document.write_bytes(b"%PDF-test")

    class Page:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class Reader:
        def __init__(self) -> None:
            self.pages = [Page("First page"), Page("Second page")]

    monkeypatch.setattr("veriagent.rag.ingest.PdfReader", lambda _: Reader())

    assert [(page.page, page.text) for page in load_document(document)] == [
        (1, "First page"),
        (2, "Second page"),
    ]


def test_chroma_ingestion_and_retrieval_return_curated_search_results(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    document = corpus_dir / "notes.txt"
    document.write_text(
        "Battery storage can shift renewable electricity between hours. " * 12,
        encoding="utf-8",
    )
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        "test_corpus",
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )
    index = CorpusIndex(
        persist_path=tmp_path / "unused",
        chunk_size=240,
        chunk_overlap=40,
        embedder=FakeEmbedder(),
        collection=collection,
    )

    result = index.ingest(document, source_root=corpus_dir, title="Storage Notes")
    hits = CorpusSearchProvider(index, top_k=2).retrieve("battery storage", limit=2)
    stored = collection.get(include=["metadatas"])

    assert result.chunks >= 2
    assert stored["metadatas"][0]["title"] == "Storage Notes"
    assert stored["metadatas"][0]["path"] == "notes.txt"
    assert stored["metadatas"][0]["page"] == 1
    assert hits
    assert hits[0].source_type == SourceType.CURATED
    assert hits[0].snapshot_text and "Battery storage" in hits[0].snapshot_text
    assert hits[0].url.startswith("corpus://")


@pytest.mark.asyncio
async def test_researcher_uses_curated_snapshot_and_extractor_verifies_quote() -> None:
    quote = "Battery storage can shift renewable electricity between hours."

    class Index:
        def query(self, query: str, limit: int) -> dict[str, Any]:
            return {
                "documents": [[quote]],
                "metadatas": [
                    [
                        {
                            "title": "Storage Notes",
                            "path": "notes.md",
                            "page": 2,
                            "chunk_index": 0,
                            "document_id": "doc-1",
                        }
                    ]
                ],
                "distances": [[0.1]],
            }

    provider = CorpusSearchProvider(Index(), top_k=1)  # type: ignore[arg-type]
    budget = BudgetGovernor(RunBudget(max_searches=2, max_fetches=2, max_llm_tokens=100))

    async def forbidden_fetch(**_: Any) -> Any:
        raise AssertionError("Curated chunks must not be fetched over the network")

    state: dict[str, Any] = {
        "claim": Claim(text="Battery storage shifts renewable electricity."),
        "subquestions": [
            SubQuestion(
                claim_id="claim-1",
                question="What can storage shift?",
                search_queries=["battery storage renewable electricity"],
            )
        ],
        "sources": [],
        "snapshots": {},
        "budget": budget,
        "recorder": None,
        "search_providers": [provider],
        "fetch_fn": forbidden_fetch,
    }
    researched = await run_researcher_node(state)  # type: ignore[arg-type]
    source = researched["sources"][0]
    snapshot = researched["snapshots"][source.id]
    extraction_state = {
        **state,
        **researched,
        "evidence": [],
        "llm": FakeLLM(
            responses={
                "extractor": {
                    "items": [
                        {
                            "quote": quote,
                            "stance": "supports",
                            "context_conditions": [],
                        }
                    ]
                }
            }
        ),
    }

    extracted = run_extractor_node(extraction_state)  # type: ignore[arg-type]

    assert source.source_type == SourceType.CURATED
    assert snapshot == quote
    assert extracted["evidence"][0].quote_verified is True


def test_corpus_upload_enforces_type_and_size_limits(tmp_path: Path) -> None:
    class RecordingIndex:
        def ingest(self, path: Path, *, source_root: Path, title: str) -> IngestResult:
            assert path.read_text(encoding="utf-8") == "Curated evidence text."
            assert path.parent == source_root
            return IngestResult("doc-1", title, path.name, 1, 1)

    app = create_app(
        settings=Settings(
            app_env="test",
            database_url="sqlite://",
            corpus_dir=str(tmp_path / "corpus"),
            chroma_path=str(tmp_path / "chroma"),
            corpus_max_document_bytes=1024,
            demo_replay_enabled=False,
            rate_limit_requests=100,
        ),
        llm=FakeLLM(),
        search_providers=[],
    )
    app.state.corpus_index = RecordingIndex()
    with TestClient(app) as client:
        accepted = client.post(
            "/api/corpus",
            files={"file": ("evidence.md", b"Curated evidence text.", "text/markdown")},
            data={"title": "Reviewed Evidence"},
        )
        rejected_type = client.post(
            "/api/corpus",
            files={"file": ("payload.exe", b"not allowed", "application/octet-stream")},
        )
        rejected_size = client.post(
            "/api/corpus",
            files={"file": ("large.txt", b"x" * 1025, "text/plain")},
        )

    assert accepted.status_code == 201
    assert accepted.json()["title"] == "Reviewed Evidence"
    assert accepted.json()["chunks"] == 1
    assert rejected_type.status_code == 415
    assert rejected_type.json()["error"]["code"] == "unsupported_corpus_type"
    assert rejected_size.status_code == 413
    assert rejected_size.json()["error"]["code"] == "corpus_file_too_large"
