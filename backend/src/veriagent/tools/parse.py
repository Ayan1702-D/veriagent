"""HTML extraction and text snapshot generation via trafilatura."""

import hashlib
from urllib.parse import urlparse

import trafilatura

from veriagent.schemas import Source, SourceType


class ParsedSnapshot:
    """Extracted text, metadata, and provenance hash of a fetched webpage."""

    def __init__(
        self,
        url: str,
        title: str,
        clean_text: str,
        date: str | None,
        snapshot_hash: str,
    ) -> None:
        self.url = url
        self.title = title
        self.clean_text = clean_text
        self.date = date
        self.snapshot_hash = snapshot_hash

    def to_source(
        self, rank_score: float = 0.5, source_type: SourceType = SourceType.SECONDARY
    ) -> Source:
        """Convert snapshot into a validated Source schema."""
        parsed = urlparse(self.url)
        domain = parsed.hostname or "unknown"
        return Source(
            url=self.url,
            title=self.title or domain,
            domain=domain,
            snapshot_hash=self.snapshot_hash,
            rank_score=rank_score,
            source_type=source_type,
        )


def parse_html_to_snapshot(raw_html: str, url: str) -> ParsedSnapshot:
    """Extract readable text, title, date from raw HTML and compute sha256 of snapshot."""
    # Note: verify trafilatura.extract parameters in official docs
    clean_text = (
        trafilatura.extract(
            raw_html,
            url=url,
            favor_recall=True,
            include_comments=False,
            include_tables=True,
        )
        or ""
    )

    metadata = trafilatura.extract_metadata(raw_html, default_url=url)
    title = (metadata.title if metadata and metadata.title else "").strip()
    date = metadata.date if metadata and metadata.date else None

    content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
    snapshot_hash = f"sha256:{content_hash}"

    return ParsedSnapshot(
        url=url,
        title=title,
        clean_text=clean_text,
        date=date,
        snapshot_hash=snapshot_hash,
    )
