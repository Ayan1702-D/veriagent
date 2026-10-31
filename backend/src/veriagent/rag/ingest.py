"""Document loading, overlapping chunking, embedding, and Chroma persistence."""

import re
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol, cast

from pypdf import PdfReader

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".txt", ".md"})


class EmbeddingModel(Protocol):
    """Subset of FastEmbed used by the corpus index."""

    def passage_embed(self, documents: list[str]) -> Iterable[Any]: ...

    def query_embed(self, query: str) -> Iterable[Any]: ...


@dataclass(frozen=True)
class LoadedPage:
    """Text extracted from one logical page of a document."""

    text: str
    page: int


@dataclass(frozen=True)
class DocumentChunk:
    """One indexed passage with stable provenance metadata."""

    id: str
    text: str
    title: str
    path: str
    page: int
    chunk_index: int
    document_id: str


@dataclass(frozen=True)
class IngestResult:
    """Summary returned after a document is indexed."""

    document_id: str
    title: str
    path: str
    pages: int
    chunks: int


def load_document(path: Path) -> list[LoadedPage]:
    """Load UTF-8 TXT/Markdown or extract text from each PDF page."""
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported corpus document type: {extension or '<none>'}")
    if extension == ".pdf":
        reader = PdfReader(str(path))
        pages = [
            LoadedPage(text=(page.extract_text() or "").strip(), page=index)
            for index, page in enumerate(reader.pages, 1)
        ]
    else:
        pages = [LoadedPage(text=path.read_text(encoding="utf-8").strip(), page=1)]
    if not any(page.text for page in pages):
        raise ValueError("Document contains no extractable text")
    return pages


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> Iterator[str]:
    """Split text into character-bounded chunks with deterministic overlap."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")
    normalized = re.sub(r"\s+", " ", text).strip()
    start = 0
    while start < len(normalized):
        hard_end = min(len(normalized), start + chunk_size)
        end = hard_end
        if hard_end < len(normalized):
            boundary = normalized.rfind(" ", start + chunk_size // 2, hard_end)
            if boundary > start:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            yield chunk
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)


def build_chunks(
    path: Path,
    *,
    source_root: Path,
    title: str | None = None,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> tuple[list[DocumentChunk], int]:
    """Load a document and create stable, page-aware chunks."""
    pages = load_document(path)
    resolved_path = path.resolve()
    resolved_root = source_root.resolve()
    try:
        relative_path = resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(
            "Corpus document must remain inside the configured corpus directory"
        ) from exc
    document_id = sha256(relative_path.encode("utf-8")).hexdigest()[:24]
    document_title = (title or path.stem).strip() or path.stem
    chunks: list[DocumentChunk] = []
    chunk_index = 0
    for page in pages:
        for text in chunk_text(page.text, chunk_size, overlap):
            chunk_id = f"{document_id}-{chunk_index:06d}"
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    text=text,
                    title=document_title,
                    path=relative_path,
                    page=page.page,
                    chunk_index=chunk_index,
                    document_id=document_id,
                )
            )
            chunk_index += 1
    if not chunks:
        raise ValueError("Document contains no indexable text")
    return chunks, len(pages)


class CorpusIndex:
    """Lazy FastEmbed and persistent Chroma index shared by ingestion and retrieval."""

    def __init__(
        self,
        *,
        persist_path: Path,
        collection_name: str = "veriagent_corpus",
        embedding_model_name: str = "BAAI/bge-small-en-v1.5",
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        embedder: EmbeddingModel | None = None,
        collection: Any | None = None,
    ) -> None:
        self.persist_path = persist_path
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._embedder = embedder
        self._collection = collection
        self._lock = threading.RLock()

    def _ensure_collection(self) -> Any:
        with self._lock:
            if self._collection is None:
                import chromadb

                self.persist_path.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(path=str(self.persist_path))
                self._collection = client.get_or_create_collection(
                    self.collection_name,
                    metadata={
                        "hnsw:space": "cosine",
                        "embedding_model": self.embedding_model_name,
                    },
                    embedding_function=None,
                )
            return self._collection

    def _ensure_embedder(self) -> EmbeddingModel:
        with self._lock:
            if self._embedder is None:
                from fastembed import TextEmbedding

                self._embedder = cast(
                    EmbeddingModel,
                    TextEmbedding(model_name=self.embedding_model_name),
                )
            return self._embedder

    @staticmethod
    def _vectors(values: Iterable[Any]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for value in values:
            raw = value.tolist() if hasattr(value, "tolist") else list(value)
            vectors.append([float(item) for item in raw])
        return vectors

    def ingest(self, path: Path, *, source_root: Path, title: str | None = None) -> IngestResult:
        """Embed and replace all chunks belonging to one corpus path."""
        chunks, page_count = build_chunks(
            path,
            source_root=source_root,
            title=title,
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
        )
        collection = self._ensure_collection()
        embedder = self._ensure_embedder()
        embeddings = self._vectors(embedder.passage_embed([chunk.text for chunk in chunks]))
        metadata = [
            {
                "title": chunk.title,
                "path": chunk.path,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "document_id": chunk.document_id,
                "source_type": "curated",
            }
            for chunk in chunks
        ]
        with self._lock:
            collection.delete(where={"path": chunks[0].path})
            collection.upsert(
                ids=[chunk.id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                metadatas=metadata,
                embeddings=embeddings,
            )
        first = chunks[0]
        return IngestResult(
            document_id=first.document_id,
            title=first.title,
            path=first.path,
            pages=page_count,
            chunks=len(chunks),
        )

    def query(self, query: str, limit: int) -> dict[str, Any]:
        """Run one dense-vector query and return the raw Chroma result."""
        collection = self._ensure_collection()
        if collection.count() == 0:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        embedder = self._ensure_embedder()
        query_embedding = self._vectors(embedder.query_embed(query))[0]
        with self._lock:
            result: dict[str, Any] = collection.query(
                query_embeddings=[query_embedding],
                n_results=max(1, limit),
                include=["documents", "metadatas", "distances"],
            )
        return result
