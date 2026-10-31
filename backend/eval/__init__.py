"""Offline-first regression evaluation for VeriAgent."""

from eval.dataset import EvalClaim, RecordedRun, load_claims
from eval.metrics import EvalReport, evaluate_runs

__all__ = ["EvalClaim", "EvalReport", "RecordedRun", "evaluate_runs", "load_claims"]
