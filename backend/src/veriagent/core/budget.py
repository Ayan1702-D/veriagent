"""Thread- and async-safe budget governor for verification runs."""

import threading
import time
from collections.abc import Callable
from typing import Literal, cast

from veriagent.core.errors import BudgetExceededError
from veriagent.schemas.models import RunBudget

BudgetKind = Literal["tokens", "searches", "fetches", "loops"]
_VALID_KINDS: frozenset[str] = frozenset({"tokens", "searches", "fetches", "loops"})


class BudgetGovernor:
    """Tracks resource usage against hard caps for a single verification run."""

    def __init__(
        self,
        budget: RunBudget,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize governor with a RunBudget and monotonic clock."""
        self._budget = budget
        self._clock = clock
        self._start_time = self._clock()
        self._lock = threading.RLock()
        self._used: dict[BudgetKind, int] = {
            "tokens": 0,
            "searches": 0,
            "fetches": 0,
            "loops": 0,
        }

    @property
    def budget(self) -> RunBudget:
        """Return the underlying RunBudget configuration."""
        return self._budget

    def _limit_for(self, kind: BudgetKind) -> int:
        """Return the configured integer cap for a discrete resource kind."""
        if kind == "tokens":
            return self._budget.max_llm_tokens
        if kind == "searches":
            return self._budget.max_searches
        if kind == "fetches":
            return self._budget.max_fetches
        return self._budget.max_loops

    def _elapsed_unlocked(self) -> float:
        """Return elapsed wall-clock seconds since governor creation."""
        return max(0.0, self._clock() - self._start_time)

    def consume(self, kind: BudgetKind, n: int = 1) -> None:
        """Consume `n` units of `kind` or raise BudgetExceeded if any cap is hit."""
        if kind not in _VALID_KINDS:
            raise ValueError(f"Unknown budget kind: {kind!r}")
        if n < 0:
            raise ValueError(f"Consumption amount must be non-negative, got {n}")

        with self._lock:
            elapsed = self._elapsed_unlocked()
            if elapsed > self._budget.max_seconds:
                raise BudgetExceededError("seconds", round(elapsed, 3), self._budget.max_seconds)

            limit = self._limit_for(kind)
            proposed = self._used[kind] + n
            if proposed > limit:
                raise BudgetExceededError(kind, proposed, limit)

            self._used[kind] = proposed

    def remaining(self) -> dict[str, float | int]:
        """Return remaining capacity across all tracked budget dimensions."""
        with self._lock:
            elapsed = self._elapsed_unlocked()
            rem_seconds = max(0.0, round(self._budget.max_seconds - elapsed, 3))
            return {
                "tokens": max(0, self._budget.max_llm_tokens - self._used["tokens"]),
                "searches": max(0, self._budget.max_searches - self._used["searches"]),
                "fetches": max(0, self._budget.max_fetches - self._used["fetches"]),
                "loops": max(0, self._budget.max_loops - self._used["loops"]),
                "seconds": rem_seconds,
            }

    def usage(self) -> dict[str, float | int]:
        """Return current consumed amounts across all tracked budget dimensions."""
        with self._lock:
            return {
                "tokens": self._used["tokens"],
                "searches": self._used["searches"],
                "fetches": self._used["fetches"],
                "loops": self._used["loops"],
                "seconds": round(self._elapsed_unlocked(), 3),
            }

    def exhausted(self) -> bool:
        """Return True if any resource cap or wall-clock timeout has been reached."""
        with self._lock:
            if self._elapsed_unlocked() >= self._budget.max_seconds:
                return True
            for key in _VALID_KINDS:
                kind = cast(BudgetKind, key)
                if self._used[kind] >= self._limit_for(kind):
                    return True
            return False
