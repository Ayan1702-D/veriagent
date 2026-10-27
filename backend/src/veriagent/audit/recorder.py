"""Ordered in-memory audit event recorder with a pluggable sink interface."""

import threading
from typing import Any, Protocol, runtime_checkable

from veriagent.schemas.models import AuditEvent


@runtime_checkable
class AuditSink(Protocol):
    """Pluggable sink interface for persisting or streaming AuditEvent objects."""

    def emit(self, event: AuditEvent) -> None:
        """Handle a newly recorded AuditEvent."""


class AuditRecorder:
    """Thread-safe recorder maintaining strictly ordered AuditEvent objects per run."""

    def __init__(self, run_id: str, sink: AuditSink | None = None) -> None:
        """Initialize recorder for `run_id` with an optional external sink."""
        if not run_id:
            raise ValueError("run_id must be a non-empty string")
        self._run_id = run_id
        self._sink = sink
        self._events: list[AuditEvent] = []
        self._seq = 0
        self._lock = threading.RLock()

    @property
    def run_id(self) -> str:
        """Return the run identifier associated with this recorder."""
        return self._run_id

    def record(
        self,
        node: str,
        type: str,
        payload: dict[str, Any] | None = None,
        tokens: int = 0,
    ) -> AuditEvent:
        """Create, store, and optionally emit the next sequential AuditEvent."""
        with self._lock:
            self._seq += 1
            event = AuditEvent(
                run_id=self._run_id,
                seq=self._seq,
                node=node,
                type=type,
                payload=dict(payload) if payload is not None else {},
                tokens=tokens,
            )
            self._events.append(event)
            sink = self._sink

        if sink is not None:
            sink.emit(event)

        return event

    def events(self) -> list[AuditEvent]:
        """Return a shallow copy of all recorded events in sequence order."""
        with self._lock:
            return list(self._events)

    def total_tokens(self) -> int:
        """Return the sum of LLM tokens logged across all recorded events."""
        with self._lock:
            return sum(e.tokens for e in self._events)
