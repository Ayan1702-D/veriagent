"""Curated corpus upload and ingestion endpoint."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from veriagent.config import Settings
from veriagent.rag import CorpusIndex
from veriagent.rag.ingest import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/api/corpus", tags=["corpus"])
logger = logging.getLogger(__name__)
_READ_BLOCK_SIZE = 64 * 1024
_ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
}


class CorpusIngestResponse(BaseModel):
    """Public summary of an indexed corpus document."""

    document_id: str
    title: str
    path: str
    pages: int
    chunks: int
    bytes: int


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _index(request: Request) -> CorpusIndex:
    return request.app.state.corpus_index  # type: ignore[no-any-return]


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    data = bytearray()
    while block := await file.read(_READ_BLOCK_SIZE):
        data.extend(block)
        if len(data) > max_bytes:
            raise _error(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "corpus_file_too_large",
                f"Corpus documents are limited to {max_bytes} bytes",
            )
    return bytes(data)


@router.post("", response_model=CorpusIngestResponse, status_code=status.HTTP_201_CREATED)
async def add_corpus_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=500)] = None,
) -> CorpusIngestResponse:
    """Validate, save, chunk, embed, and index one PDF, TXT, or Markdown document."""
    settings = _settings(request)
    if not settings.corpus_enabled:
        raise _error(503, "corpus_disabled", "Curated corpus ingestion is disabled")

    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    if not original_name or extension not in SUPPORTED_EXTENSIONS:
        raise _error(415, "unsupported_corpus_type", "Only PDF, TXT, and MD files are accepted")
    media_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in _ALLOWED_CONTENT_TYPES[extension]:
        raise _error(
            415,
            "unsupported_corpus_type",
            f"Content type {media_type or '<missing>'!r} is not valid for {extension}",
        )

    try:
        content = await _read_limited(file, settings.corpus_max_document_bytes)
    finally:
        await file.close()
    if not content:
        raise _error(422, "empty_corpus_document", "Uploaded document is empty")

    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", original_name).strip(" .")[:160]
    if not safe_name:
        safe_name = f"document{extension}"
    corpus_dir = Path(settings.corpus_dir).resolve()
    corpus_dir.mkdir(parents=True, exist_ok=True)
    destination = (corpus_dir / safe_name).resolve()
    if destination.parent != corpus_dir:
        raise _error(400, "invalid_corpus_path", "Invalid corpus filename")

    await asyncio.to_thread(destination.write_bytes, content)
    try:
        result = await asyncio.to_thread(
            _index(request).ingest,
            destination,
            source_root=corpus_dir,
            title=(title.strip() if title and title.strip() else Path(original_name).stem),
        )
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        raise _error(422, "corpus_ingest_failed", str(exc)) from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        logger.exception("Corpus indexing failed for %s", safe_name)
        raise _error(
            500,
            "corpus_index_unavailable",
            "The corpus index could not process this document",
        ) from exc

    return CorpusIngestResponse(**result.__dict__, bytes=len(content))
