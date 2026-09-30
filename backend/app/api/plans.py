from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entities import User
from app.schemas.plan import PlanSchema, PlanUpdateRequest
from app.services.planning_service import planning_service
from app.security.auth import get_current_user

router = APIRouter(prefix="/plans", tags=["Plans"])

class GeneratePlanRequest(BaseModel):
    goal_id: str

@router.post("/generate", response_model=PlanSchema)
async def generate_plan(
    req: GeneratePlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Decomposes an understood goal into an executable task graph plan,
    resolving candidate tools and evaluating real risk per task.
    """
    try:
        plan = await planning_service.create_plan_for_goal(
            goal_id=req.goal_id,
            user_id=current_user.id,
            db=db
        )
        return plan
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate plan: {str(e)}"
        )

@router.get("/{plan_id}", response_model=PlanSchema)
async def get_plan(
    plan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves an existing plan and its tasks."""
    try:
        return await planning_service.get_plan(plan_id, current_user.id, db)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
