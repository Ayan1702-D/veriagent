"""LiteLLM client wrapper with retries, Pydantic JSON validation, caching, and audit hooks."""

import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

import litellm
from pydantic import BaseModel, ValidationError

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.core.errors import BudgetExceededError, VeriAgentError
from veriagent.llm.cache import CassetteCache, CassetteMissError
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
        fallback_models: Sequence[str] = (),
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
        self._fallback_models = tuple(
            candidate.strip() for candidate in fallback_models if candidate.strip()
        )

    def _call_with_backoff(
        self,
        node: str,
        model: str,
        messages: list[dict[str, str]],
        budget: BudgetGovernor | None = None,
        deadline: float | None = None,
    ) -> tuple[str, int, bool, str]:
        """Return content and the model used, trying the configured fallback chain in order."""
        models = tuple(dict.fromkeys((model, *self._fallback_models)))
        last_err: Exception | None = None
        for candidate in models:
            try:
                cached = self._cache.get(node, candidate, messages)
            except CassetteMissError as exc:
                last_err = exc
                continue
            if cached is not None:
                return cached.content, cached.tokens, True, candidate

            for attempt in range(self._max_retries):
                remaining = budget.remaining() if budget is not None else None
                if budget is not None and remaining is not None and remaining["seconds"] <= 0:
                    raise BudgetExceededError(
                        "seconds", budget.usage()["seconds"], budget.budget.max_seconds
                    )
                call_seconds = deadline - time.monotonic() if deadline is not None else 12.0
                if call_seconds <= 0:
                    raise VeriAgentError(f"Structured LLM operation timed out for node={node!r}")
                request_timeout = (
                    max(0.1, min(12.0, call_seconds, float(remaining["seconds"]) - 0.1))
                    if remaining
                    else min(12.0, call_seconds)
                )
                output_cap = min(1200, int(remaining["tokens"])) if remaining else 1200
                if output_cap < 1 and budget is not None:
                    raise BudgetExceededError(
                        "tokens", budget.usage()["tokens"], budget.budget.max_llm_tokens
                    )
                try:
                    raw_resp = self._completion_fn(
                        model=candidate,
                        messages=messages,
                        response_format={"type": "json_object"},
                        timeout=request_timeout,
                        max_tokens=output_cap,
                        num_retries=0,
                    )
                    content, tokens = _extract_content_and_tokens(raw_resp)
                    self._cache.put(node, candidate, messages, content, tokens)
                    return content, tokens, False, candidate
                except Exception as exc:
                    last_err = exc
                    if type(exc).__name__ in {
                        "AuthenticationError",
                        "BadRequestError",
                        "NotFoundError",
                        "RateLimitError",
                        "ServiceUnavailableError",
                        "Timeout",
                        "APITimeoutError",
                        "TimeoutError",
                    }:
                        break
                    if attempt + 1 < self._max_retries:
                        delay = min(self._max_delay, self._base_delay * (2**attempt))
                        if deadline is not None:
                            delay = min(delay, max(0.0, deadline - time.monotonic()))
                        self._sleep(delay)

        if self._cache.mode == "replay" and isinstance(last_err, CassetteMissError):
            raise last_err

        raise VeriAgentError(
            f"LLM call failed for node={node!r} across {len(models)} configured model(s) "
            f"({type(last_err).__name__ if last_err is not None else 'UnknownError'})"
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

        # One structured operation includes provider fallback and JSON repair.
        # Bound the whole operation so repair cannot spend the next stages' time.
        call_window = min(12.0, float(budget.remaining()["seconds"]) / 3) if budget else 12.0
        deadline = time.monotonic() + call_window
        model = self._router.model_for(node)
        original_messages = [dict(m) for m in messages]
        working_messages = [dict(m) for m in messages]
        schema = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
        schema_instruction = f"Return only JSON: a JSON object matching this schema: {schema}"
        if working_messages and working_messages[0]["role"] == "system":
            working_messages[0]["content"] += f"\n\n{schema_instruction}"
        else:
            working_messages.insert(0, {"role": "system", "content": schema_instruction})

        for validation_attempt in range(2):
            try:
                content, tokens, from_cache, used_model = self._call_with_backoff(
                    node, model, working_messages, budget, deadline
                )
            except CassetteMissError:
                if self._cache.mode != "replay" or validation_attempt:
                    raise
                # Older demo cassettes were recorded before schema instructions
                # were included in the prompt.
                working_messages = original_messages
                content, tokens, from_cache, used_model = self._call_with_backoff(
                    node, model, working_messages, budget, deadline
                )
            except BudgetExceededError:
                raise
            except VeriAgentError as exc:
                if validation_attempt:
                    failure_kind = type(exc.__cause__ or exc).__name__
                    raise LLMOutputValidationError(
                        f"{node.capitalize()} returned invalid JSON and the repair call failed "
                        f"({failure_kind}). Check model availability or retry."
                    ) from exc
                raise

            if budget is not None:
                budget.consume("tokens", tokens)

            if recorder is not None:
                recorder.record(
                    node=node,
                    type="llm_call",
                    payload={
                        "model": used_model,
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
                issues = [
                    {"path": ".".join(map(str, issue["loc"])) or "$", "type": issue["type"]}
                    for issue in val_err.errors()
                ]
                if recorder is not None:
                    recorder.record(
                        node=node,
                        type="llm_validation_failed",
                        payload={
                            "attempt": validation_attempt + 1,
                            "response_model": response_model.__name__,
                            "issue_count": len(issues),
                            "issues": issues,
                        },
                    )
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
                    f"Output validation failed for {response_model.__name__} in node={node!r}: "
                    + ", ".join(f"{issue['path']} ({issue['type']})" for issue in issues)
                ) from val_err

        raise LLMOutputValidationError(f"Unreachable validation state for node={node!r}")
