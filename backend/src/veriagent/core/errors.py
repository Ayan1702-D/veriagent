"""Custom exception hierarchy for VeriAgent."""


class VeriAgentError(Exception):
    """Base exception for all VeriAgent domain errors."""


class BudgetExceededError(VeriAgentError):
    """Raised when a run exceeds any configured budget cap."""

    def __init__(self, kind: str, used: float, limit: float) -> None:
        self.kind = kind
        self.used = used
        self.limit = limit
        super().__init__(f"Budget exceeded for '{kind}': {used} > {limit}")


class SecurityViolationError(VeriAgentError):
    """Raised when an input or URL violates security policy (e.g., SSRF)."""