"""Curated local corpus ingestion and retrieval."""

from veriagent.rag.ingest import CorpusIndex, IngestResult, build_chunks, chunk_text, load_document
from veriagent.rag.retriever import CorpusSearchProvider

__all__ = [
    "CorpusIndex",
    "CorpusSearchProvider",
    "IngestResult",
    "build_chunks",
    "chunk_text",
    "load_document",
]
