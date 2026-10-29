"""Source independence and deduplication: detects syndicated articles and mirrors."""

from collections.abc import Sequence

from rapidfuzz import fuzz

from veriagent.schemas import Source


class DeduplicatedCluster:
    """Represents a set of syndicated or near-duplicate documents resolved to one primary source."""

    def __init__(self, canonical_source: Source, duplicate_sources: list[Source]) -> None:
        self.canonical_source = canonical_source
        self.duplicate_sources = duplicate_sources


def deduplicate_sources(
    source_snapshots: Sequence[tuple[Source, str]],
    similarity_threshold: float = 85.0,
) -> list[DeduplicatedCluster]:
    """Group near-duplicate text into clusters, keeping the highest-ranked source canonical."""
    clusters: list[list[tuple[Source, str]]] = []

    for src, text in source_snapshots:
        sample = text[:3000].strip().lower()

        matched_cluster = None
        for cluster in clusters:
            canon_src, canon_text = cluster[0]
            canon_sample = canon_text[:3000].strip().lower()

            # Fast match: same snapshot hash
            if src.snapshot_hash == canon_src.snapshot_hash:
                matched_cluster = cluster
                break

            # Near duplicate detection: rapidfuzz token sort ratio
            ratio = fuzz.token_sort_ratio(sample, canon_sample)
            if ratio >= similarity_threshold:
                matched_cluster = cluster
                break

        if matched_cluster is not None:
            matched_cluster.append((src, text))
        else:
            clusters.append([(src, text)])

    result: list[DeduplicatedCluster] = []
    for cluster in clusters:
        # Sort cluster by rank_score descending; winner is canonical
        cluster.sort(key=lambda item: item[0].rank_score, reverse=True)
        canonical = cluster[0][0]
        duplicates = [item[0] for item in cluster[1:]]
        result.append(DeduplicatedCluster(canonical_source=canonical, duplicate_sources=duplicates))

    return result
