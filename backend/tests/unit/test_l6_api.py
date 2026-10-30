"""L6 API, persistence, SSE, replay, and security tests."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from veriagent.config import Settings
from veriagent.core.budget import BudgetGovernor
from veriagent.llm.fake import FakeLLM
from veriagent.main import create_app
from veriagent.tools.fetch import FetchedDocument
from veriagent.tools.search.base import SearchResult


class FakeSearchProvider:
    """Canned provider that still accounts for search budget."""

    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def search(
        self,
        query: str,
        limit: int = 5,
        budget: BudgetGovernor | None = None,
        recorder: Any = None,
    ) -> list[SearchResult]:
        self.calls += 1
        if budget is not None:
            budget.consume("searches")
        return [
            SearchResult(
                title="Grid Emissions Study",
                url="https://example.org/grid-study",
                snippet="Lifecycle emissions depend on grid mix.",
                provider=self.name,
            )
        ]


async def fake_fetch(
    url: str,
    budget: BudgetGovernor | None = None,
    recorder: Any = None,
    **_: Any,
) -> FetchedDocument:
    """Return a deterministic document without network access."""
    if budget is not None:
        budget.consume("fetches")
    return FetchedDocument(
        url=url,
        content=(
            "<html><head><title>Grid Study</title></head><body>"
            "<p>Electric vehicles have lower lifetime emissions on renewable grids.</p>"
            "</body></html>"
        ),
        status_code=200,
        content_type="text/html",
    )


def build_fake_llm() -> FakeLLM:
    """Return graph responses for a single successful run."""
    return FakeLLM(
        responses={
            "planner": {
                "qualifiers": [],
                "atomic_subclaims": ["EV emissions depend on grid mix"],
                "subquestions": ["How does grid mix affect EV emissions?"],
                "search_queries": [["EV emissions grid mix"]],
            },
            "extractor": {
                "items": [
                    {
                        "quote": (
                            "Electric vehicles have lower lifetime emissions on renewable grids."
                        ),
                        "stance": "supports",
                        "context_conditions": ["renewable grids"],
                    }
                ]
            },
            "contradiction": {
                "subclaim_findings": [
                    {
                        "subclaim": "EV emissions depend on grid mix",
                        "supporting_evidence_ids": [],
                        "contradicting_evidence_ids": [],
                        "gaps": [],
                        "verdict": "SUPPORTED",
                        "confidence": 0.9,
                    }
                ]
            },
            "verifier": [
                {"evaluations": []},
                {"queries": []},
            ],
            "reporter": {
                "overall_verdict": "SUPPORTED",
                "limitations": ["One source in test fixture."],
                "cited_source_ids": ["https://example.org/grid-study"],
            },
        },
        tokens_per_call=10,
    )


@pytest.fixture
def api_client() -> tuple[TestClient, FakeLLM, FakeSearchProvider]:
    """Create an isolated in-memory API client."""
    llm = build_fake_llm()
    provider = FakeSearchProvider()
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        cors_origins=["https://frontend.example"],
        max_llm_tokens=1000,
        max_searches=5,
        max_fetches=5,
        max_loops=1,
        max_seconds=30,
        rate_limit_requests=100,
    )
    app = create_app(
        settings=settings,
        llm=llm,
        search_providers=[provider],
        fetch_fn=fake_fetch,
    )
    with TestClient(app) as client:
        yield client, llm, provider


def test_run_lifecycle_sse_audit_and_budget_cap(
    api_client: tuple[TestClient, FakeLLM, FakeSearchProvider],
) -> None:
    """Create a run, persist its report, stream it, and expose its audit trail."""
    client, _, provider = api_client
    created = client.post(
        "/api/runs",
        json={
            "claim": "EV emissions depend on grid mix.",
            "budget": {"max_llm_tokens": 99999, "max_searches": 999},
        },
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]

    run = client.get(f"/api/runs/{run_id}")
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "completed"
    assert body["budget"]["max_llm_tokens"] == 1000
    assert body["budget"]["max_searches"] == 5
    assert body["report"]["verdict"] == "SUPPORTED"
    assert body["report"]["citations"][0]["url"] == "https://example.org/grid-study"
    assert provider.calls == 1

    audit = client.get(f"/api/runs/{run_id}/audit")
    assert audit.status_code == 200
    events = audit.json()["events"]
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "run_completed"

    stream = client.get(f"/api/runs/{run_id}/stream")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: audit" in stream.text
    assert "event: end" in stream.text
    assert '"status":"completed"' in stream.text


def test_replay_is_offline_and_reuses_persisted_report(
    api_client: tuple[TestClient, FakeLLM, FakeSearchProvider],
) -> None:
    """Replay creates a new completed run without more LLM or search calls."""
    client, llm, provider = api_client
    original = client.post("/api/runs", json={"claim": "EV grid emissions vary."})
    original_id = original.json()["run_id"]
    llm_calls = len(llm.calls)
    search_calls = provider.calls

    replay = client.post(f"/api/runs/{original_id}/replay")
    assert replay.status_code == 202
    replay_id = replay.json()["run_id"]
    replay_run = client.get(f"/api/runs/{replay_id}").json()
    assert replay_run["status"] == "completed"
    assert replay_run["replay_of"] == original_id
    assert replay_run["budget_usage"]["tokens"] == 0
    assert replay_run["report"] == client.get(f"/api/runs/{original_id}").json()["report"]
    assert len(llm.calls) == llm_calls
    assert provider.calls == search_calls

    event_types = [
        event["type"] for event in client.get(f"/api/runs/{replay_id}/audit").json()["events"]
    ]
    assert event_types == ["replay_started", "replay_completed"]


def test_validation_not_found_health_and_cors(
    api_client: tuple[TestClient, FakeLLM, FakeSearchProvider],
) -> None:
    """Expose consistent errors, health, and configured CORS policy."""
    client, _, _ = api_client
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    invalid = client.post("/api/runs", json={"claim": "  "})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"

    missing = client.get("/api/runs/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "run_not_found"

    preflight = client.options(
        "/api/runs",
        headers={
            "Origin": "https://frontend.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://frontend.example"


def test_rate_limit_has_standard_error_envelope() -> None:
    """Reject excess per-IP requests with a predictable 429 response."""
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
    )
    app = create_app(settings=settings, llm=build_fake_llm(), search_providers=[])
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        limited = client.get("/health")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"
    assert "retry-after" in limited.headers
