"""Deterministic fuzzy quote verification against stored snapshot text."""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass(frozen=True)
class MatchResult:
    """Outcome of a fuzzy quote search against a stored document snapshot."""

    found: bool
    score: float
    span: tuple[int, int] | None


def _normalize_text(text: str) -> str:
    """Normalize Unicode, optional quotation marks, case, and whitespace."""
    normalized = unicodedata.normalize("NFKD", text)

    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
    for orig, rep in replacements.items():
        normalized = normalized.replace(orig, rep)

    # Treat quotation marks around words as optional for quote matching.
    normalized = re.sub(r"""(['"])(.*?)\1""", r"\2", normalized)

    return re.sub(r"\s+", " ", normalized).strip()


def verify_quote(
    quote: str,
    snapshot_text: str,
    threshold: float = 85.0,
) -> MatchResult:
    """Fuzzy-match quote against stored snapshot without an LLM.

    Returns MatchResult indicating whether the quote exists, the match score (0-100),
    and the approximate (start, end) character span in the snapshot.
    """
    clean_quote = _normalize_text(quote)
    clean_snapshot = _normalize_text(snapshot_text)

    if not clean_quote or not clean_snapshot:
        return MatchResult(found=False, score=0.0, span=None)

    quote_lower = clean_quote.casefold()
    snapshot_lower = clean_snapshot.casefold()

    # Exact match after Unicode and whitespace normalization.
    exact_idx = snapshot_lower.find(quote_lower)
    if exact_idx != -1:
        return MatchResult(
            found=True,
            score=100.0,
            span=(exact_idx, exact_idx + len(clean_quote)),
        )

    # Fuzzy matching fallback.

    alignment = fuzz.partial_ratio_alignment(quote_lower, snapshot_lower)

    if alignment is None:
        return MatchResult(found=False, score=0.0, span=None)

    score = round(float(alignment.score), 2)

    if score >= threshold:
        span = (alignment.dest_start, alignment.dest_end)
        return MatchResult(found=True, score=score, span=span)

    return MatchResult(found=False, score=score, span=None)
