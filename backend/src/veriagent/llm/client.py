"""LiteLLM client wrapper with retries, Pydantic JSON validation, caching, and audit hooks."""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

import litellm
from pydantic import BaseModel, ValidationError

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.core.errors import VeriAgentError
from veriagent.llm.cache import CassetteCache
from veriagent.llm.router import ModelRouter

T = TypeVar("T", bound=BaseModel)
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class LLMOutputValidationError(VeriAgentError):
    """Raised when LLM output fails Pydantic validation after the retry attempt."""


@runtime_checkable
class LLMProtocol(Protocol):
    """Common interface implemented by both LLMClient and FakeLLM."""

    def complete(
        self,
        node: str,
        messages: list[dict[str, str]],
        response_model: type[T],
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> T:
        """Execute a structured completion and return a validated `response_model`."""


def load_prompt(node: str) -> str:
    """Load the markdown system prompt for `node` from `llm/prompts/{node}.md`."""
    path = _PROMPTS_DIR / f"{node}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found for node {node!r}: {path}")
    return path.read_text(encoding="utf-8").strip()


def _strip_json_fences(text: str) -> str:
    """Strip optional ```json ... ``` markdown fences around JSON strings."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _extract_content_and_tokens(response: Any) -> tuple[str, int]:
    """Extract string content and total token usage from a LiteLLM response object or dict."""
    if isinstance(response, dict):
        choices = response.get("choices", [])
        content = str(choices[0]["message"]["content"]) if choices else ""
        usage = response.get("usage") or {}
        tokens = int(usage.get("total_tokens", 0))
        return content, max(0, tokens)

    choices = getattr(response, "choices", [])
    content = str(choices[0].message.content) if choices else ""
    usage = getattr(response, "usage", None)
    tokens = int(getattr(usage, "total_tokens", 0) or 0) if usage is not None else 0
    return content, max(0, tokens)


class LLMClient:
    """Structured LLM client using LiteLLM, CassetteCache, BudgetGovernor, and AuditRecorder."""

    def __init__(
        self,
        router: ModelRouter,
        cache: CassetteCache | None = None,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 4.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        completion_fn: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize client with router, optional cassette cache, and retry backoff."""
        self._router = router
        self._cache = cache if cache is not None else CassetteCache(mode="live")
        self._max_retries = max(1, max_retries)
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep_fn
        # Note: verify litellm.completion kwargs in official LiteLLM docs when upgrading
        self._completion_fn = completion_fn or litellm.completion

    def _call_with_backoff(
        self,
        node: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> tuple[str, int, bool]:
        """Return (content, tokens, from_cache) using cache or retrying LiteLLM with backoff."""
        cached = self._cache.get(node, model, messages)
        if cached is not None:
            return cached.content, cached.tokens, True

        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                raw_resp = self._completion_fn(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                content, tokens = _extract_content_and_tokens(raw_resp)
                self._cache.put(node, model, messages, content, tokens)
                return content, tokens, False
            except Exception as exc:
                last_err = exc
                if attempt + 1 < self._max_retries:
                    delay = min(self._max_delay, self._base_delay * (2**attempt))
                    self._sleep(delay)

        raise VeriAgentError(
            f"LLM call failed after {self._max_retries} attempts for node={node!r}"
        ) from last_err

    def complete(
        self,
        node: str,
        messages: list[dict[str, str]],
        response_model: type[T],
        budget: BudgetGovernor | None = None,
        recorder: AuditRecorder | None = None,
    ) -> T:
        """Call the routed LLM, validate against `response_model` (retry once), and log usage."""
        if budget is not None and budget.exhausted():
            budget.consume("tokens", 1)

        model = self._router.model_for(node)
        working_messages = [dict(m) for m in messages]

        for validation_attempt in range(2):
            content, tokens, from_cache = self._call_with_backoff(node, model, working_messages)

            if budget is not None:
                budget.consume("tokens", tokens)

            if recorder is not None:
                recorder.record(
                    node=node,
                    type="llm_call",
                    payload={
                        "model": model,
                        "attempt": validation_attempt + 1,
                        "cached": from_cache,
                        "response_model": response_model.__name__,
                    },
                    tokens=tokens,
                )

            cleaned = _strip_json_fences(content)
            try:
                return response_model.model_validate_json(cleaned)
            except ValidationError as val_err:
                if validation_attempt == 0:
                    working_messages = [
                        *working_messages,
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                "Your previous JSON response failed schema validation: "
                                f"{val_err}. Return ONLY valid JSON matching the schema."
                            ),
                        },
                    ]
                    continue
                raise LLMOutputValidationError(
                    f"Output validation failed for {response_model.__name__} in node={node!r}"
                ) from val_err

        raise LLMOutputValidationError(f"Unreachable validation state for node={node!r}")
