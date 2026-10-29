"""Public exports for the verification layer."""

from veriagent.verification.entailment import (
    apply_unsupported_claim_rule,
    build_counter_queries,
    check_support,
)
from veriagent.verification.quote_match import MatchResult, verify_quote

__all__ = [
    "MatchResult",
    "apply_unsupported_claim_rule",
    "build_counter_queries",
    "check_support",
    "verify_quote",
]
