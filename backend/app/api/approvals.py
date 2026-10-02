from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.entities import Approval, Execution, User
from app.schemas.execution import ApprovalSchema
from app.security.auth import get_current_user
from app.security.crypto import hash_payload

router = APIRouter(prefix="/approvals", tags=["Approvals"])

class ApprovalDecisionRequest(BaseModel):
    decision: str  # "approved" | "rejected"
    payload_hash: Optional[str] = None
    reason: Optional[str] = None
    decided_by: str = "ui"  # "ui" | "voice"

@router.get("", response_model=List[ApprovalSchema])
async def list_approvals(
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lists approval requests for the current user, optionally filtered by status."""
    stmt = (
        select(Approval)
        .join(Execution, Approval.execution_id == Execution.id)
        .where(Execution.user_id == current_user.id)
        .order_by(Approval.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(Approval.status == status_filter)

    res = await db.execute(stmt)
    approvals = res.scalars().all()
    return approvals

@router.post("/{approval_id}/decide", response_model=ApprovalSchema)
async def decide_approval(
    approval_id: str,
    req: ApprovalDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submits user decision (approve or reject) for a pending approval request.
    Server-side gating ensures execution only resumes with exact approved payload.
    """
    stmt = (
        select(Approval)
        .join(Execution, Approval.execution_id == Execution.id)
        .where(Approval.id == approval_id, Execution.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    approval = res.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")

    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Approval is already {approval.status}.")

    decision_norm = req.decision.strip().lower()
    if decision_norm not in ["approved", "rejected"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Decision must be 'approved' or 'rejected'.")

    decided_by_norm = req.decided_by.strip().lower()
    if decided_by_norm not in ["ui", "voice", "cli", "api"]:
        decided_by_norm = "ui"

    # Verify cryptographic payload integrity
    stored_hash = approval.payload_hash
    computed_hash = hash_payload(approval.content)
    if stored_hash != computed_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload integrity verification failed: approval content does not match stored hash."
        )

    if req.payload_hash and req.payload_hash != stored_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided payload hash does not match the approval request."
        )

    approval.status = decision_norm
    approval.decided_by = decided_by_norm
    approval.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(approval)

    return approval

