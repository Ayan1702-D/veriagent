"""Deployment settings and deterministic demo fallback tests."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from veriagent.config import Settings
from veriagent.demo import DEMO_RUNS
from veriagent.llm.fake import FakeLLM
from veriagent.main import create_app


def test_production_cors_requires_explicit_https_origins() -> None:
    with pytest.raises(ValidationError, match="explicit HTTPS origins"):
        Settings(app_env="production", cors_origins=["*"])
    with pytest.raises(ValidationError, match="explicit HTTPS origins"):
        Settings(app_env="production", cors_origins=["http://localhost:3000"])

    settings = Settings(app_env="production", cors_origins=["https://veriagent.example"])

    assert settings.cors_origins == ["https://veriagent.example"]


def test_default_budget_is_conservative_for_free_tiers() -> None:
    budget = Settings().default_budget()

    assert budget.max_llm_tokens == 6000
    assert budget.max_searches == 4
    assert budget.max_fetches == 6
    assert budget.max_loops == 1
    assert budget.max_seconds == 45.0


def test_demo_claim_auto_replays_without_live_dependencies() -> None:
    app = create_app(
        settings=Settings(
            app_env="test",
            database_url="sqlite://",
            demo_replay_enabled=True,
            rate_limit_requests=100,
        ),
        llm=FakeLLM(),
        search_providers=[],
    )
    with TestClient(app) as client:
        created = client.post("/api/runs", json={"claim": DEMO_RUNS[0].claim.text})
        assert created.status_code == 202
        run = client.get(f"/api/runs/{created.json()['run_id']}")

    body = run.json()
    assert body["status"] == "completed"
    assert body["replay_of"] == DEMO_RUNS[0].run_id
    assert body["budget_usage"]["tokens"] == 0
    assert body["budget_usage"]["searches"] == 0
    assert body["report"]["verdict"] == "CONDITIONAL"


def test_seeded_source_supports_explicit_replay_endpoint() -> None:
    app = create_app(
        settings=Settings(
            app_env="test",
            database_url="sqlite://",
            demo_replay_enabled=True,
            rate_limit_requests=100,
        ),
        llm=FakeLLM(),
        search_providers=[],
    )
    with TestClient(app) as client:
        replay = client.post(f"/api/runs/{DEMO_RUNS[2].run_id}/replay")
        assert replay.status_code == 202
        run = client.get(f"/api/runs/{replay.json()['run_id']}").json()

    assert run["status"] == "completed"
    assert run["replay_of"] == DEMO_RUNS[2].run_id
    assert run["report"]["verdict"] == "REFUTED"
