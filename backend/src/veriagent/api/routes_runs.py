"""Run creation, inspection, streaming, audit, and replay routes."""

import asyncio
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from veriagent.api.schemas import (
    AuditResponse,
    BudgetRequest,
    CreateRunRequest,
    RunAcceptedResponse,
    RunResponse,
)
from veriagent.api.service import RunService
from veriagent.config import Settings
from veriagent.demo import demo_run_id_for_claim
from veriagent.schemas import Claim, RunBudget

router = APIRouter(prefix="/api/runs", tags=["runs"])
_TERMINAL_STATUSES = {"completed", "failed"}


def _service(request: Request) -> RunService:
    return request.app.state.run_service  # type: ignore[no-any-return]


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _not_found(run_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "run_not_found", "message": f"Run {run_id!r} was not found"},
    )


def _capped_budget(requested: BudgetRequest | None, settings: Settings) -> RunBudget:
    """Apply client overrides without allowing server cap escalation."""
    defaults = settings.default_budget()
    if requested is None:
        return defaults
    values = requested.model_dump(exclude_none=True)
    capped: dict[str, int | float] = {}
    for field, value in values.items():
        capped[field] = min(value, getattr(defaults, field))
    return defaults.model_copy(update=capped)


def _run_response(service: RunService, run_id: str) -> RunResponse:
    row = service.repository.get_run(run_id)
    if row is None:
        raise _not_found(run_id)
    return RunResponse(
        run_id=row.id,
        status=row.status,  # type: ignore[arg-type]
        claim=row.claim_json,
        budget=row.budget_json,
        budget_usage=service.budget_usage(run_id),
        replay_of=row.replay_of,
        report=service.repository.get_report(run_id),
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=RunAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: CreateRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> RunAcceptedResponse:
    """Queue a claim verification run."""
    service = _service(request)
    budget = _capped_budget(body.budget, _settings(request))
    claim = Claim(text=body.claim)
    run_id = uuid4().hex
    demo_source_id = (
        demo_run_id_for_claim(body.claim) if _settings(request).demo_replay_enabled else None
    )
    demo_source = service.repository.get_run(demo_source_id) if demo_source_id is not None else None
    if demo_source_id is not None and demo_source is not None and demo_source.status == "completed":
        service.repository.create_run(run_id, claim, budget, replay_of=demo_source_id)
        background_tasks.add_task(service.execute_replay, run_id, demo_source_id)
    else:
        service.repository.create_run(run_id, claim, budget)
        background_tasks.add_task(service.execute, run_id, claim, budget)
    return RunAcceptedResponse(run_id=run_id)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request) -> RunResponse:
    """Return lifecycle state and the final report when available."""
    return _run_response(_service(request), run_id)


@router.get("/{run_id}/audit", response_model=AuditResponse)
async def get_audit(run_id: str, request: Request) -> AuditResponse:
    """Return the complete ordered audit log."""
    service = _service(request)
    if service.repository.get_run(run_id) is None:
        raise _not_found(run_id)
    return AuditResponse(
        run_id=run_id,
        events=service.repository.list_audit_events(run_id),
    )


@router.post(
    "/{run_id}/replay",
    response_model=RunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replay_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
) -> RunAcceptedResponse:
    """Queue an offline replay from persisted artifacts."""
    service = _service(request)
    source = service.repository.get_run(run_id)
    if source is None:
        raise _not_found(run_id)
    if source.status != "completed" or service.repository.get_report(run_id) is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "run_not_replayable",
                "message": "Only a completed run with a report can be replayed",
            },
        )
    replay_id = uuid4().hex
    claim = Claim.model_validate(source.claim_json)
    budget = RunBudget.model_validate(source.budget_json)
    service.repository.create_run(replay_id, claim, budget, replay_of=run_id)
    background_tasks.add_task(service.execute_replay, replay_id, run_id)
    return RunAcceptedResponse(run_id=replay_id)


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    """Stream audit events and live budget usage until the run terminates."""
    service = _service(request)
    if service.repository.get_run(run_id) is None:
        raise _not_found(run_id)

    async def event_stream() -> Any:
        last_seq = 0
        while True:
            if await request.is_disconnected():
                return
            events = service.repository.list_audit_events(run_id, after_seq=last_seq)
            for event in events:
                last_seq = event.seq
                data = {
                    "event": event.model_dump(mode="json"),
                    "budget_usage": service.budget_usage(run_id),
                }
                yield (
                    f"id: {event.seq}\n"
                    f"event: audit\n"
                    f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
                )

            row = service.repository.get_run(run_id)
            if row is None:
                return
            if row.status in _TERMINAL_STATUSES:
                terminal = {
                    "run_id": run_id,
                    "status": row.status,
                    "budget_usage": service.budget_usage(run_id),
                }
                yield f"event: end\ndata: {json.dumps(terminal, separators=(',', ':'))}\n\n"
                return
            await asyncio.sleep(0.05)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
