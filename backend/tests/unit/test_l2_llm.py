"""Unit tests for the L2 LLM layer: router, cassette cache, LLMClient, and FakeLLM."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from veriagent.audit.recorder import AuditRecorder
from veriagent.config import Settings
from veriagent.core.budget import BudgetGovernor
from veriagent.core.errors import BudgetExceededError
from veriagent.llm import (
    CassetteCache,
    CassetteMissError,
    FakeLLM,
    LLMClient,
    LLMOutputValidationError,
    ModelRouter,
    load_prompt,
)
from veriagent.schemas import RunBudget, Verdict


class SamplePlanOutput(BaseModel):
    """Minimal schema for testing structured LLM completions."""

    qualifiers: list[str]
    subclaims: list[str]
    verdict_hint: Verdict = Verdict.INSUFFICIENT


def test_router_maps_cheap_and_strong_models_from_settings() -> None:
    """Verify ModelRouter reads model names strictly from Settings."""
    settings = Settings(
        cheap_model="groq/llama-3.1-8b-instant",
        strong_model="gemini/gemini-1.5-pro",
    )
    router = ModelRouter(settings)

    assert router.model_for("planner") == "groq/llama-3.1-8b-instant"
    assert router.model_for("extractor") == "groq/llama-3.1-8b-instant"
    assert router.model_for("verifier") == "groq/llama-3.1-8b-instant"
    assert router.model_for("contradiction") == "gemini/gemini-1.5-pro"
    assert router.model_for("reporter") == "gemini/gemini-1.5-pro"

    with pytest.raises(ValueError, match="Unknown LLM node"):
        router.model_for("unknown_node")


def test_prompt_stubs_exist_and_load() -> None:
    """Verify all five node prompt markdown files exist and are non-empty."""
    for node in ("planner", "extractor", "contradiction", "verifier", "reporter"):
        prompt = load_prompt(node)
        assert len(prompt) > 20
        assert "JSON" in prompt


def test_fake_llm_tracks_budget_and_audit() -> None:
    """Verify FakeLLM returns validated Pydantic models and logs tokens/events."""
    fake = FakeLLM(
        responses={
            "planner": {
                "qualifiers": ["always"],
                "subclaims": ["Subclaim 1"],
                "verdict_hint": "CONDITIONAL",
            }
        },
        tokens_per_call=42,
    )
    budget = BudgetGovernor(RunBudget(max_llm_tokens=100))
    recorder = AuditRecorder(run_id="run-fake-1")
    messages = [{"role": "user", "content": "Decompose claim"}]

    result = fake.complete(
        node="planner",
        messages=messages,
        response_model=SamplePlanOutput,
        budget=budget,
        recorder=recorder,
    )

    assert result.qualifiers == ["always"]
    assert result.verdict_hint == Verdict.CONDITIONAL
    assert budget.remaining()["tokens"] == 58
    events = recorder.events()
    assert len(events) == 1
    assert events[0].node == "planner"
    assert events[0].type == "llm_call"
    assert events[0].tokens == 42
    assert len(fake.calls) == 1


def test_cassette_cache_record_and_replay(tmp_path: Path) -> None:
    """Verify LLMClient records a cassette on first run and replays offline without network."""
    settings = Settings(cheap_model="test/cheap-v1", strong_model="test/strong-v1")
    router = ModelRouter(settings)
    messages = [{"role": "user", "content": "Check EV emissions"}]

    call_counter = 0

    def fake_completion(**kwargs: Any) -> dict[str, Any]:
        nonlocal call_counter
        call_counter += 1
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"qualifiers": ["regardless"], "subclaims": ["Grid mix"]}'
                    }
                }
            ],
            "usage": {"total_tokens": 35},
        }

    # 1. Record mode writes cassette to tmp_path
    record_cache = CassetteCache(mode="record", cassette_dir=tmp_path)
    record_client = LLMClient(
        router=router,
        cache=record_cache,
        completion_fn=fake_completion,
    )
    budget_rec = BudgetGovernor(RunBudget(max_llm_tokens=500))
    recorder_rec = AuditRecorder(run_id="run-record")

    out1 = record_client.complete(
        node="planner",
        messages=messages,
        response_model=SamplePlanOutput,
        budget=budget_rec,
        recorder=recorder_rec,
    )
    assert out1.qualifiers == ["regardless"]
    assert call_counter == 1
    assert len(list(tmp_path.glob("*.json"))) == 1

    # 2. Replay mode reads cassette without invoking completion_fn
    def fail_if_called(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Network completion should not be called in replay mode")

    replay_cache = CassetteCache(mode="replay", cassette_dir=tmp_path)
    replay_client = LLMClient(
        router=router,
        cache=replay_cache,
        completion_fn=fail_if_called,
    )
    budget_rep = BudgetGovernor(RunBudget(max_llm_tokens=500))
    recorder_rep = AuditRecorder(run_id="run-replay")

    out2 = replay_client.complete(
        node="planner",
        messages=messages,
        response_model=SamplePlanOutput,
        budget=budget_rep,
        recorder=recorder_rep,
    )
    assert out2 == out1
    assert budget_rep.usage()["tokens"] == 35
    assert recorder_rep.events()[0].payload["cached"] is True

    # 3. Replay mode raises CassetteMissError on unseen prompt
    with pytest.raises(CassetteMissError):
        replay_client.complete(
            node="planner",
            messages=[{"role": "user", "content": "Unseen prompt"}],
            response_model=SamplePlanOutput,
        )


def test_llm_client_retries_on_transient_error_and_validation_failure() -> None:
    """Verify LLMClient backs off on transient errors and retries once on invalid JSON."""
    settings = Settings(cheap_model="test/cheap", strong_model="test/strong")
    router = ModelRouter(settings)
    sleeps: list[float] = []
    attempts = 0

    def flaky_completion(**kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("Rate limit 429")
        if attempts == 2:
            # First returned JSON is invalid (missing required 'subclaims' field)
            return {
                "choices": [{"message": {"content": '{"qualifiers": ["always"]}'}}],
                "usage": {"total_tokens": 10},
            }
        # Validation retry returns valid JSON wrapped in markdown fences
        return {
            "choices": [
                {
                    "message": {
                    "content": '```json\n{"qualifiers": ["always"], "subclaims": ["Fixed"]}\n```'
                    }
                }
            ],
            "usage": {"total_tokens": 15},
        }

    client = LLMClient(
        router=router,
        cache=CassetteCache(mode="live"),
        base_delay=0.25,
        sleep_fn=sleeps.append,
        completion_fn=flaky_completion,
    )
    budget = BudgetGovernor(RunBudget(max_llm_tokens=100))
    recorder = AuditRecorder(run_id="run-retry")

    result = client.complete(
        node="extractor",
        messages=[{"role": "user", "content": "Extract"}],
        response_model=SamplePlanOutput,
        budget=budget,
        recorder=recorder,
    )

    assert result.subclaims == ["Fixed"]
    assert attempts == 3
    assert sleeps == [0.25]
    assert budget.usage()["tokens"] == 25
    assert len(recorder.events()) == 2


def test_llm_client_raises_validation_error_after_second_bad_output() -> None:
    """Verify LLMClient raises LLMOutputValidationError if repair retry also fails validation."""
    settings = Settings()
    router = ModelRouter(settings)

    def always_invalid(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": '{"not_a_valid_field": 123}'}}],
            "usage": {"total_tokens": 10},
        }

    client = LLMClient(router=router, completion_fn=always_invalid)
    with pytest.raises(LLMOutputValidationError):
        client.complete(
            node="verifier",
            messages=[{"role": "user", "content": "Verify"}],
            response_model=SamplePlanOutput,
        )


def test_llm_client_respects_budget_cap() -> None:
    """Verify LLMClient raises BudgetExceeded when token usage crosses the cap."""
    settings = Settings()
    router = ModelRouter(settings)

    def costly_completion(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": '{"qualifiers": [], "subclaims": ["A"]}'}}],
            "usage": {"total_tokens": 80},
        }

    client = LLMClient(router=router, completion_fn=costly_completion)
    budget = BudgetGovernor(RunBudget(max_llm_tokens=50))

    with pytest.raises(BudgetExceededError) as exc_info:
        client.complete(
            node="planner",
            messages=[{"role": "user", "content": "Plan"}],
            response_model=SamplePlanOutput,
            budget=budget,
        )
    assert exc_info.value.kind == "tokens"
