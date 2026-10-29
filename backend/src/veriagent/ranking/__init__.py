"""Public exports for ranking and source deduplication."""

from veriagent.ranking.dedupe import DeduplicatedCluster, deduplicate_sources
from veriagent.ranking.scorer import SourceScorer

__all__ = ["DeduplicatedCluster", "SourceScorer", "deduplicate_sources"]
