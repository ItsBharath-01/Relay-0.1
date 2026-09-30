from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.entities import Connection, Permission
from app.tools.registry import get_tools_for_capability, get_tool, BaseTool
from app.security.crypto import decrypt_secret

class ToolCheckResult(BaseModel):
    tool_id: str
    tool_name: str
    tool_type: str
    is_connected: bool
    is_authorized: bool
    is_available: bool
    is_compatible: bool
    passed_all: bool
    ruled_out_reason: Optional[str] = None

class SelectionDecisionRecord(BaseModel):
    task_id: Optional[str] = None
    capability_id: str
    candidate_checks: List[ToolCheckResult]
    selected_tool_id: Optional[str]
    selected_tool_name: Optional[str]
    explanation: str

class ToolSelectionEngine:
    """
    Deterministic tool selection engine enforcing real connection,
    permission, availability, and compatibility checks.
    """

    async def evaluate_candidates(
        self,
        user_id: str,
        capability_id: str,
        db: AsyncSession,
        task_id: Optional[str] = None,
        excluded_tool_ids: Optional[List[str]] = None,
    ) -> SelectionDecisionRecord:
        excluded = set(excluded_tool_ids or [])
        candidate_tools = get_tools_for_capability(capability_id)

        # Query user connections with permissions
        stmt = select(Connection).options(selectinload(Connection.permissions)).where(Connection.user_id == user_id)
        res = await db.execute(stmt)
        user_conns: Dict[str, Connection] = {c.app_id: c for c in res.scalars().all()}

        checks: List[ToolCheckResult] = []
        eligible_tools: List[Tuple[BaseTool, str]] = []

        for tool in candidate_tools:
            if tool.id in excluded:
                checks.append(ToolCheckResult(
                    tool_id=tool.id,
                    tool_name=tool.name,
                    tool_type=tool.tool_type,
                    is_connected=False,
                    is_authorized=False,
                    is_available=False,
                    is_compatible=True,
                    passed_all=False,
                    ruled_out_reason="Excluded due to prior failure in recovery flow."
                ))
                continue

            # Check 1: Compatibility
            is_compatible = capability_id in tool.provides

            # Check 2: Connection
            is_connected = True
            raw_credentials = None
            conn = None
            if tool.requires_connection:
                conn = user_conns.get(tool.requires_connection)
                if not conn or conn.status != "connected":
                    is_connected = False
                elif conn.encrypted_credentials:
                    raw_credentials = decrypt_secret(conn.encrypted_credentials)

            # Check 3: Authorization (Permissions)
            is_authorized = True
            if tool.requires_connection and conn:
                granted_keys = {p.permission_key for p in conn.permissions if p.is_granted}
                for req_perm in tool.required_permissions:
                    if req_perm not in granted_keys:
                        is_authorized = False
                        break

            # Check 4: Availability / Health
            is_available = False
            health_msg = None
            if is_connected and is_authorized and is_compatible:
                is_available, health_msg = await tool.health_check(raw_credentials)

            passed_all = is_compatible and is_connected and is_authorized and is_available
            ruled_out = None
            if not is_compatible:
                ruled_out = f"Does not support capability '{capability_id}'."
            elif not is_connected:
                ruled_out = f"Application '{tool.name}' is not connected."
            elif not is_authorized:
                ruled_out = f"Missing required permissions ({', '.join(tool.required_permissions)})."
            elif not is_available:
                ruled_out = f"Health check failed: {health_msg or 'Unreachable'}."

            check_res = ToolCheckResult(
                tool_id=tool.id,
                tool_name=tool.name,
                tool_type=tool.tool_type,
                is_connected=is_connected,
                is_authorized=is_authorized,
                is_available=is_available,
                is_compatible=is_compatible,
                passed_all=passed_all,
                ruled_out_reason=ruled_out
            )
            checks.append(check_res)

            if passed_all:
                eligible_tools.append((tool, raw_credentials or ""))

        # Rank eligible tools deterministically: API > browser > connector > mcp
        type_rank = {"api": 1, "browser": 2, "connector": 3, "mcp": 4}
        eligible_tools.sort(key=lambda t: type_rank.get(t[0].tool_type, 99))

        if eligible_tools:
            selected_tool, _ = eligible_tools[0]
            explanation = (
                f"{selected_tool.name} was selected because it is connected, authorized, "
                f"passed all health checks, and natively supports '{capability_id}'."
            )
            return SelectionDecisionRecord(
                task_id=task_id,
                capability_id=capability_id,
                candidate_checks=checks,
                selected_tool_id=selected_tool.id,
                selected_tool_name=selected_tool.name,
                explanation=explanation
            )
        else:
            explanation = (
                f"No connected tool can perform '{capability_id}'. "
                "Connect an appropriate application in Connections to proceed."
            )
            return SelectionDecisionRecord(
                task_id=task_id,
                capability_id=capability_id,
                candidate_checks=checks,
                selected_tool_id=None,
                selected_tool_name=None,
                explanation=explanation
            )

selection_engine = ToolSelectionEngine()
