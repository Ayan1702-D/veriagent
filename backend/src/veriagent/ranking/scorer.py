"""Multi-factor source scoring: authority tiers, recency, and primary-source heuristic."""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

from veriagent.schemas import SourceType

_DOMAINS_YAML_PATH = Path(__file__).resolve().parent / "domains.yaml"


class SourceScorer:
    """Computes a bounded rank score [0.0, 1.0] and reasoning for a candidate source."""

    def __init__(self, rules_path: Path | None = None) -> None:
        """Load domain classification rules from YAML."""
        path = rules_path or _DOMAINS_YAML_PATH
        if path.is_file():
            self._rules = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            self._rules = {}

        self.high = set(self._rules.get("high_trust", []))
        self.medium = set(self._rules.get("medium_trust", []))
        self.low = set(self._rules.get("low_trust", []))
        self.penalized = set(self._rules.get("penalized", []))

    def _domain_match(self, domain: str, targets: set[str]) -> bool:
        """Check if domain ends with or matches any target rule."""
        domain = domain.lower()
        for t in targets:
            t = t.lower()
            if domain == t or domain.endswith(t) or domain.endswith("." + t.lstrip(".")):
                return True
        return False

    def classify_source_type(self, domain: str) -> SourceType:
        """Heuristically assign SourceType enum."""
        if self._domain_match(domain, self.high):
            return SourceType.PRIMARY
        if self._domain_match(domain, self.medium):
            return SourceType.NEWS
        if self._domain_match(domain, self.low):
            return SourceType.BLOG
        return SourceType.SECONDARY

    def score(
        self,
        url: str,
        date_str: str | None = None,
        is_primary_heuristic: bool = False,
    ) -> tuple[float, str, SourceType]:
        """Compute score [0.0, 1.0], reason string, and inferred SourceType."""
        domain = (urlparse(url).hostname or "").lower()
        source_type = self.classify_source_type(domain)

        # 1. Authority base score
        if self._domain_match(domain, self.penalized):
            auth_score = 0.1
            tier = "penalized"
        elif self._domain_match(domain, self.high):
            auth_score = 0.85
            tier = "high_trust"
        elif self._domain_match(domain, self.medium):
            auth_score = 0.65
            tier = "medium_trust"
        elif self._domain_match(domain, self.low):
            auth_score = 0.35
            tier = "low_trust"
        else:
            auth_score = 0.50
            tier = "standard_web"

        reasons = [f"domain tier: {tier} ({auth_score:.2f})"]

        # 2. Recency modifier (+0.05 to +0.10 for recent, small decay if old)
        recency_bonus = 0.0
        if date_str:
            try:
                year = int(date_str[:4])
                current_year = datetime.now(UTC).year
                diff = current_year - year
                if diff <= 2:
                    recency_bonus = 0.10
                    reasons.append("recent publication (<=2y, +0.10)")
                elif diff <= 5:
                    recency_bonus = 0.05
                    reasons.append("moderately recent (<=5y, +0.05)")
                elif diff > 10:
                    recency_bonus = -0.05
                    reasons.append("older publication (>10y, -0.05)")
            except (ValueError, TypeError):
                pass

        # 3. Primary source heuristic boost
        primary_bonus = 0.0
        if is_primary_heuristic or source_type == SourceType.PRIMARY:
            primary_bonus = 0.10
            reasons.append("primary source bonus (+0.10)")

        raw_score = auth_score + recency_bonus + primary_bonus
        final_score = max(0.0, min(1.0, round(raw_score, 3)))
        reason_str = "; ".join(reasons)

        return final_score, reason_str, source_type
