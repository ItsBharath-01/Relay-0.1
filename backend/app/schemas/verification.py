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
