from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class FailureDiagnosis(BaseModel):
    failure_type: str = Field(
        ...,
        description="Category: 'auth' | 'permission' | 'rate_limit' | 'network' | 'timeout' | 'invalid_input' | 'not_found' | 'verification_failed' | 'unknown'"
    )
    cause: str = Field(..., description="Root cause of the failure")
    recoverable: bool = Field(..., description="Whether this task failure is recoverable")
    affected_task: str = Field(..., description="Task title or ID")
    recommended_strategy: str = Field(
        ...,
        description="'retry_with_backoff' | 'alternative_tool' | 'alternative_params' | 'replan_remaining' | 'reconnect_required' | 'abort'"
    )

class RecoveryPlan(BaseModel):
    strategy: str = Field(
        ...,
        description="'retry_with_backoff' | 'alternative_tool' | 'alternative_params' | 'replan_remaining' | 'abort'"
    )
    alternative_capability: Optional[str] = Field(None, description="Valid capability ID to attempt")
    alternative_tool: Optional[str] = Field(None, description="Tool ID to execute")
    updated_action: Optional[str] = Field(None, description="Action name to execute")
    updated_params: Dict[str, Any] = Field(default_factory=dict, description="Sanitized parameters for recovery action")
    reason: str = Field(..., description="Explanation for this recovery plan")
    expected_result: str = Field(..., description="Expected verification outcome")
