import json
import asyncio
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db, async_session_maker
from app.models.entities import Execution, Plan, Goal, User, ExecutionEvent, Approval, Recovery, Verification
from app.schemas.execution import ExecutionDetailSchema, StartExecutionRequest
from app.agent.execution_runner import execution_runner
from app.events.manager import event_broadcaster
from app.security.auth import get_current_user, get_user_from_stream

router = APIRouter(prefix="/executions", tags=["Executions"])

@router.post("/start", response_model=ExecutionDetailSchema)
async def start_execution(
    req: StartExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Starts autonomous execution of a plan with real tools, verification, and approval gates."""
    stmt = (
        select(Plan)
        .join(Goal, Plan.goal_id == Goal.id)
        .options(selectinload(Plan.tasks), selectinload(Plan.goal))
        .where(Plan.id == req.plan_id, Goal.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    execution = Execution(
        goal_id=plan.goal_id,
        plan_id=plan.id,
        user_id=current_user.id,
        status="running",
        progress=0.0
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # Launch background state machine
    await execution_runner.start_execution_background(execution.id)

    return ExecutionDetailSchema(
        id=execution.id,
        goal_id=plan.goal_id,
        goal_text=plan.goal.text,
        plan_id=plan.id,
        status=execution.status,
        outcome=execution.outcome,
        evidence_level=execution.evidence_level,
        outcome_summary=execution.outcome_summary,
        progress=execution.progress,
        started_at=execution.started_at,
        events=[],
        approvals=[],
        recoveries=[],
        verifications=[]
    )

@router.get("/{execution_id}", response_model=ExecutionDetailSchema)
async def get_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves current execution state, audit timeline events, approvals, and evidence."""
    stmt = (
        select(Execution)
        .options(
            selectinload(Execution.goal),
            selectinload(Execution.events),
            selectinload(Execution.approvals),
            selectinload(Execution.recoveries),
            selectinload(Execution.verifications)
        )
        .where(Execution.id == execution_id, Execution.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    execution = res.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")

    return ExecutionDetailSchema(
        id=execution.id,
        goal_id=execution.goal_id,
        goal_text=execution.goal.text if execution.goal else "",
        plan_id=execution.plan_id,
        status=execution.status,
        outcome=execution.outcome,
        evidence_level=execution.evidence_level,
        outcome_summary=execution.outcome_summary,
        progress=execution.progress,
        current_task_id=execution.current_task_id,
        current_action=execution.current_action,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        events=[
            {
                "id": e.id,
                "seq": e.seq,
                "type": e.type,
                "timestamp": e.timestamp,
                "task_id": e.task_id,
                "tool_id": e.tool_id,
                "message": e.message,
                "params": e.params or {},
                "payload": e.payload or {}
            } for e in execution.events
        ],
        approvals=[
            {
                "id": a.id,
                "execution_id": a.execution_id,
                "task_id": a.task_id,
                "action": a.action,
                "target": a.target,
                "content": a.content,
                "payload_hash": a.payload_hash,
                "reason": a.reason,
                "risk": a.risk,
                "consequences": a.consequences,
                "status": a.status,
                "decided_by": a.decided_by,
                "created_at": a.created_at
            } for a in execution.approvals
        ],
        recoveries=[
            {
                "id": r.id,
                "task_id": r.task_id,
                "original_tool_id": r.original_tool_id,
                "problem": r.problem,
                "alternative_tool_id": r.alternative_tool_id,
                "reason": r.reason,
                "status": r.status,
                "created_at": r.created_at
            } for r in execution.recoveries
        ],
        verifications=[
            {
                "id": v.id,
                "task_id": v.task_id,
                "criterion": v.criterion,
                "result": v.result,
                "evidence": v.evidence or {},
                "created_at": v.created_at
            } for v in execution.verifications
        ]
    )

@router.get("/{execution_id}/events")
async def stream_events(
    execution_id: str,
    request: Request,
    token: Optional[str] = None,
    current_user: User = Depends(get_user_from_stream),
    db: AsyncSession = Depends(get_db)
):
    """
    Real SSE event stream for live execution monitoring.
    Requires authentication and verifies execution ownership.
    Supports reconnection and replay from Last-Event-ID.
    """
    # Verify execution exists and belongs to current_user
    exec_stmt = select(Execution).where(Execution.id == execution_id, Execution.user_id == current_user.id)
    exec_res = await db.execute(exec_stmt)
    execution_obj = exec_res.scalar_one_or_none()
    if not execution_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found or access denied.")

    last_event_id_str = request.headers.get("Last-Event-ID")
    last_seq = int(last_event_id_str) if last_event_id_str and last_event_id_str.isdigit() else 0

    async def event_generator():
        # 1. Replay missed events from database if client reconnected
        async with async_session_maker() as db:
            stmt = (
                select(ExecutionEvent)
                .where(ExecutionEvent.execution_id == execution_id, ExecutionEvent.seq > last_seq)
                .order_by(ExecutionEvent.seq.asc())
            )
            res = await db.execute(stmt)
            past_events = res.scalars().all()
            for e in past_events:
                event_data = {
                    "id": e.id,
                    "seq": e.seq,
                    "type": e.type,
                    "timestamp": e.timestamp.isoformat(),
                    "task_id": e.task_id,
                    "tool_id": e.tool_id,
                    "message": e.message,
                    "params": e.params or {},
                    "payload": e.payload or {}
                }
                yield f"id: {e.seq}\nevent: {e.type}\ndata: {json.dumps(event_data)}\n\n"

        # 2. Stream real-time events as they occur
        queue = event_broadcaster.subscribe(execution_id)
        try:
            while True:
                # Check client disconnect
                if await request.is_disconnected():
                    break
                try:
                    event_dict = await asyncio.wait_for(queue.get(), timeout=15.0)
                    seq = event_dict.get("seq", 0)
                    evt_type = event_dict.get("type", "message")
                    yield f"id: {seq}\nevent: {evt_type}\ndata: {json.dumps(event_dict)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive comment
                    yield ": keep-alive\n\n"
        finally:
            event_broadcaster.unsubscribe(execution_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/{execution_id}/pause")
async def pause_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Execution).where(Execution.id == execution_id, Execution.user_id == current_user.id)
    res = await db.execute(stmt)
    execution = res.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    if execution.status == "running":
        execution.status = "paused"
        await db.commit()
    return {"status": "paused", "execution_id": execution_id}

@router.post("/{execution_id}/resume")
async def resume_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Execution).where(Execution.id == execution_id, Execution.user_id == current_user.id)
    res = await db.execute(stmt)
    execution = res.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    if execution.status == "paused":
        execution.status = "running"
        await db.commit()
        await event_broadcaster.emit(db, execution_id, "execution_resumed", "Execution resumed by user.")
    return {"status": "resumed", "execution_id": execution_id}

@router.post("/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Execution).where(Execution.id == execution_id, Execution.user_id == current_user.id)
    res = await db.execute(stmt)
    execution = res.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    execution.status = "cancelled"
    execution.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "cancelled", "execution_id": execution_id}
