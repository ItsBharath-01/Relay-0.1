from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class PlanTaskSchema(BaseModel):
    id: str
    order: int
    title: str
    capability_id: str
    candidate_tool_ids: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical
    requires_approval: bool = False
    status: str = "pending"
    has_connected_tool: bool = True
    selected_tool_id: Optional[str] = None
    selected_tool_name: Optional[str] = None
    action: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)

class PlanSchema(BaseModel):
    id: str
    goal_id: str
    version: int = 1
    tasks: List[PlanTaskSchema]
    all_tools_available: bool = True
    missing_capabilities: List[str] = Field(default_factory=list)

class PlanTaskUpdateRequest(BaseModel):
    id: Optional[str] = None
    order: int
    title: str
    capability_id: str
    depends_on: List[str] = Field(default_factory=list)

class PlanUpdateRequest(BaseModel):
    tasks: List[PlanTaskUpdateRequest]
