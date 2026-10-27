"""Structured JSON logging with context-local run_id propagation."""

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

_run_id_ctx: ContextVar[str | None] = ContextVar("veriagent_run_id", default=None)


def set_run_id(run_id: str | None) -> Token[str | None]:
    """Bind a run_id to the current execution context."""
    return _run_id_ctx.set(run_id)


def reset_run_id(token: Token[str | None]) -> None:
    """Restore the previous run_id in the execution context."""
    _run_id_ctx.reset(token)


def get_run_id() -> str | None:
    """Return the active run_id from the current execution context."""
    return _run_id_ctx.get()


class JsonLogFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects including run_id."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a LogRecord to a JSON string."""
        explicit_run_id = getattr(record, "run_id", None)
        run_id = explicit_run_id if explicit_run_id is not None else get_run_id()

        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": run_id,
        }
        node = getattr(record, "node", None)
        if node is not None:
            payload["node"] = node

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with structured JSON output on stdout."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    root.handlers.clear()
    root.addHandler(handler)
