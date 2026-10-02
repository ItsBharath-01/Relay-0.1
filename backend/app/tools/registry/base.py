from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Union, Iterator
from pydantic import BaseModel, Field


class EffectClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    IDEMPOTENT_WRITE = "IDEMPOTENT_WRITE"
    NON_IDEMPOTENT_WRITE = "NON_IDEMPOTENT_WRITE"
    IRREVERSIBLE = "IRREVERSIBLE"


class ActionSpec(BaseModel):
    action: str
    capability_id: str
    effect_class: EffectClass
    reversible: bool = False
    target_param: Optional[str] = None
    required_permission: Optional[str] = None
    param_schema: Dict[str, Any] = Field(default_factory=dict)
    supports_idempotency_key: bool = False


class ExecutionContext(BaseModel):
    user_id: Optional[str] = None
    execution_id: Optional[str] = None
    task_id: Optional[str] = None
    connection_id: Optional[str] = None
    credentials: Any = None  # Opaque, resolved server-side
    idempotency_key: Optional[str] = None
    approved_payload_hash: Optional[str] = None


def normalize_execution_context(ctx: Any = None, credentials: Any = None) -> ExecutionContext:
    if isinstance(ctx, ExecutionContext):
        return ctx
    if ctx is not None:
        return ExecutionContext(credentials=ctx)
    return ExecutionContext(credentials=credentials)


class ToolResult(BaseModel):
    status: str = "success"  # "success" | "error"
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    side_effect_state: Optional[str] = None  # "PENDING" | "SENT" | "CONFIRMED" | "UNCERTAIN" | "FAILED_NO_EFFECT"
    external_ids: List[str] = Field(default_factory=list)
    redacted_raw: Optional[Any] = None

    def __getitem__(self, item: str) -> Any:
        if item == "status":
            return self.status
        if item == "error":
            return self.error
        if item == "data":
            return self.data
        if item == "side_effect_state":
            return self.side_effect_state
        if item == "external_ids":
            return self.external_ids
        if item == "redacted_raw":
            return self.redacted_raw
        if item in self.data:
            return self.data[item]
        raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, item: str) -> bool:
        if item in ("status", "error", "data", "side_effect_state", "external_ids", "redacted_raw"):
            return getattr(self, item) is not None
        return item in self.data

    def items(self):
        d = dict(self.data)
        d["status"] = self.status
        if self.error is not None:
            d["error"] = self.error
        if self.side_effect_state is not None:
            d["side_effect_state"] = self.side_effect_state
        if self.external_ids:
            d["external_ids"] = self.external_ids
        return d.items()

    def keys(self):
        return [k for k, _ in self.items()]

    def values(self):
        return [v for _, v in self.items()]

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.data)
        d["status"] = self.status
        if self.error:
            d["error"] = self.error
        if self.side_effect_state:
            d["side_effect_state"] = self.side_effect_state
        if self.external_ids:
            d["external_ids"] = self.external_ids
        if self.redacted_raw:
            d["redacted_raw"] = self.redacted_raw
        return d


class VerificationOutcome(BaseModel):
    result: str = "passed"  # "passed" | "failed" | "not_verifiable"
    evidence: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None

    def __iter__(self) -> Iterator[Any]:
        # Tuple unpacking compatibility: passed, evidence = outcome
        yield (self.result == "passed")
        yield self.evidence

    def __getitem__(self, index: int) -> Any:
        if index == 0:
            return (self.result == "passed")
        elif index == 1:
            return self.evidence
        raise IndexError("VerificationOutcome index out of range")


class BaseTool(ABC):
    """Abstract interface that every real tool adapter implements in Relay."""

    id: str
    name: str
    tool_type: str  # "api" | "browser" | "connector" | "mcp" | "local"
    provides: List[str]  # Capability IDs provided by this tool
    requires_connection: Optional[str] = None  # app_id needed in user connections
    required_permissions: List[str] = []

    @abstractmethod
    def describe_actions(self) -> List[ActionSpec]:
        """Declares all ActionSpecs for this tool."""
        pass

    @abstractmethod
    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Verifies tool health and connection readiness.
        Returns: (is_healthy, error_or_status_message)
        """
        pass

    @abstractmethod
    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        ctx: ExecutionContext
    ) -> ToolResult:
        """
        Executes a real action using the tool.
        Returns ToolResult.
        """
        pass

    @abstractmethod
    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Union[ToolResult, Dict[str, Any]],
        ctx: ExecutionContext
    ) -> VerificationOutcome:
        """
        Independently checks real system state to verify intended outcome.
        Returns: VerificationOutcome(result in {passed, failed, not_verifiable}, evidence, reason)
        """
        pass
