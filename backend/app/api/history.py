from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.entities import Execution, Goal, User, ExecutionEvent, Approval, Recovery, Verification
from app.schemas.execution import ExecutionDetailSchema
from app.security.auth import get_current_user

router = APIRouter(prefix="/history", tags=["History"])

class ExecutionSummaryItem(BaseModel):
    id: str
    goal_id: str
    goal_text: str
    status: str
    outcome: Optional[str] = None
    evidence_level: Optional[str] = None
    outcome_summary: Optional[str] = None
    progress: float
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    recoveries_count: int = 0
    approvals_count: int = 0

@router.get("", response_model=List[ExecutionSummaryItem])
async def list_history(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lists past and active executions for the user with filters and search."""
    stmt = (
        select(Execution)
        .join(Goal, Execution.goal_id == Goal.id)
        .options(
            selectinload(Execution.goal),
            selectinload(Execution.recoveries),
            selectinload(Execution.approvals)
        )
        .where(Execution.user_id == current_user.id)
        .order_by(Execution.started_at.desc())
    )

    if status_filter and status_filter != "all":
        stmt = stmt.where(Execution.status == status_filter)

    if search:
        stmt = stmt.where(Goal.text.ilike(f"%{search}%"))

    res = await db.execute(stmt)
    executions = res.scalars().all()

    items = []
    for e in executions:
        dur = None
        if e.completed_at and e.started_at:
            c_at = e.completed_at
            s_at = e.started_at
            if c_at.tzinfo is not None and s_at.tzinfo is None:
                s_at = s_at.replace(tzinfo=timezone.utc)
            elif c_at.tzinfo is None and s_at.tzinfo is not None:
                c_at = c_at.replace(tzinfo=timezone.utc)
            dur = round(max(0.0, (c_at - s_at).total_seconds()), 1)
        items.append(ExecutionSummaryItem(
            id=e.id,
            goal_id=e.goal_id,
            goal_text=e.goal.text if e.goal else "",
            status=e.status,
            outcome=e.outcome,
            evidence_level=e.evidence_level,
            outcome_summary=e.outcome_summary,
            progress=e.progress,
            started_at=e.started_at,
            completed_at=e.completed_at,
            duration_seconds=dur,
            recoveries_count=len(e.recoveries),
            approvals_count=len(e.approvals)
        ))
    return items

@router.get("/{execution_id}/audit-summary")
async def get_audit_summary(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generates a plain-text markdown audit trail summary for copying."""
    stmt = (
        select(Execution)
        .options(
            selectinload(Execution.goal),
            selectinload(Execution.events),
            selectinload(Execution.verifications),
            selectinload(Execution.recoveries),
            selectinload(Execution.approvals)
        )
        .where(Execution.id == execution_id, Execution.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    execution = res.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")

    lines = [
        f"# Relay Audit Summary: Execution {execution.id}",
        f"**Goal**: {execution.goal.text if execution.goal else 'N/A'}",
        f"**Status**: {execution.status.upper()}",
        f"**Outcome**: {execution.outcome or 'N/A'}",
        f"**Evidence Level**: {execution.evidence_level or 'N/A'}",
        f"**Outcome Summary**: {execution.outcome_summary or 'N/A'}",
        f"**Started At**: {execution.started_at}",
        f"**Completed At**: {execution.completed_at or 'In Progress'}",
        "\n## Execution Audit Timeline",
    ]

    for ev in execution.events:
        lines.append(f"- `[{ev.timestamp.strftime('%H:%M:%S')}]` **{ev.type}**: {ev.message}")

    if execution.verifications:
        lines.append("\n## Independent Verifications")
        for v in execution.verifications:
            lines.append(f"- **{v.criterion}**: {v.result.upper()} (Evidence: {v.evidence})")

    if execution.recoveries:
        lines.append("\n## Recoveries")
        for r in execution.recoveries:
            lines.append(f"- Failed tool: {r.original_tool_id} -> Alternative: {r.alternative_tool_id} ({r.status})")

    return {"summary_markdown": "\n".join(lines)}
