from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class VerificationResult(BaseModel):
    criterion: str
    method: str
    result: str  # "passed" | "failed" | "not_verifiable"
    evidence: Dict[str, Any] = Field(default_factory=dict)
    details: Optional[str] = None
    checked_at: datetime = Field(default_factory=utc_now)

class GoalCriterionEvaluation(BaseModel):
    criterion: str
    status: str  # "met" | "unmet" | "not_verifiable"
    evidence: Dict[str, Any] = Field(default_factory=dict)
    reason: str

class GoalVerificationResult(BaseModel):
    goal_outcome: str  # "COMPLETED" | "PARTIALLY_COMPLETED" | "FAILED" | "BLOCKED" | "STOPPED" | "CANCELLED"
    evidence_level: str  # "ACTION_REQUESTED" | "ACTION_EXECUTED" | "ACTION_VERIFIED" | "GOAL_ACHIEVED"
    criteria_evaluations: list[GoalCriterionEvaluation] = Field(default_factory=list)
    summary: str
    checked_at: datetime = Field(default_factory=utc_now)

