from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class ExecutionEventSchema(BaseModel):
    id: str
    seq: int
    type: str
    timestamp: datetime
    task_id: Optional[str] = None
    tool_id: Optional[str] = None
    message: str
    params: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)

class ApprovalSchema(BaseModel):
    id: str
    execution_id: str
    task_id: str
    action: str
    target: Optional[str] = None
    content: Dict[str, Any]
    payload_hash: str
    reason: str
    risk: str
    consequences: Optional[str] = None
    status: str
    decided_by: Optional[str] = None
    created_at: datetime

class RecoverySchema(BaseModel):
    id: str
    task_id: str
    original_tool_id: str
    problem: str
    alternative_tool_id: Optional[str] = None
    reason: str
    status: str
    created_at: datetime

class VerificationSchema(BaseModel):
    id: str
    task_id: str
    criterion: str
    result: str
    evidence: Dict[str, Any]
    created_at: datetime

class ExecutionDetailSchema(BaseModel):
    id: str
    goal_id: str
    goal_text: str
    plan_id: str
    status: str
    progress: float
    current_task_id: Optional[str] = None
    current_action: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    events: List[ExecutionEventSchema] = Field(default_factory=list)
    approvals: List[ApprovalSchema] = Field(default_factory=list)
    recoveries: List[RecoverySchema] = Field(default_factory=list)
    verifications: List[VerificationSchema] = Field(default_factory=list)

class StartExecutionRequest(BaseModel):
    plan_id: str
