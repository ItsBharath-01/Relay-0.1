from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple

class BaseTool(ABC):
    """Abstract interface that every real tool adapter implements in Relay."""

    id: str
    name: str
    tool_type: str  # "api" | "browser" | "connector" | "mcp"
    provides: List[str]  # Capability IDs provided by this tool
    requires_connection: Optional[str] = None  # app_id needed in user connections
    required_permissions: List[str] = []

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
        credentials: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a real action using the tool.
        Returns real tool result dictionary.
        """
        pass

    @abstractmethod
    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Independently checks real system state to verify intended outcome.
        Returns: (passed, evidence_dict)
        """
        pass
