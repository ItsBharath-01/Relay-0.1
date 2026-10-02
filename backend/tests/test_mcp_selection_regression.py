import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.selection.engine import ToolSelectionEngine
from app.models.entities import Connection, Permission

pytestmark = pytest.mark.asyncio


def make_mcp_connection(
    conn_id: str,
    user_id: str,
    status: str = "connected",
    tool_name: str = "custom_tool",
    cap_id: str = "custom_capability_action",
    perms: list = None
) -> Connection:
    conn = Connection()
    conn.id = conn_id
    conn.user_id = user_id
    conn.app_id = "mcp"
    conn.name = "Test MCP Server"
    conn.status = status
    conn.auth_type = "url"
    conn.encrypted_credentials = "enc_val" if status == "connected" else None
    conn.discovered_tools = [
        {
            "tool_id": f"mcp:{conn_id}:{tool_name}",
            "name": tool_name,
            "description": "Performs custom action",
            "capability_id": cap_id,
            "capability_label": "Custom Action",
            "risk_profile": "low",
            "input_schema": {"type": "object", "properties": {"arg": {"type": "string"}}},
        }
    ]
    conn.scopes = [cap_id]
    
    perm_objs = []
    keys = perms if perms is not None else ["call_tools", "list_tools"]
    for k in keys:
        p = Permission()
        p.connection_id = conn_id
        p.permission_key = k
        p.is_granted = True
        perm_objs.append(p)
    conn.permissions = perm_objs
    return conn


def make_mock_db(connections: list) -> AsyncMock:
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = connections
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


async def test_mcp_dynamic_tool_registration_and_selection():
    """Verifies that an MCP connection's discovered tools are dynamically registered and selected."""
    conn_id = str(uuid.uuid4())
    user_id = "user-123"
    conn = make_mcp_connection(conn_id, user_id, "connected", "custom_tool", "custom_capability_action")
    db = make_mock_db([conn])

    with patch("app.selection.engine.decrypt_secret", return_value='{"server_url": "http://localhost:8085/mcp"}'):
        with patch("app.tools.adapters.mcp_client.mcp_client.health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = (True, {"message": "Healthy"})
            engine = ToolSelectionEngine()
            decision = await engine.evaluate_candidates(
                user_id=user_id,
                capability_id="custom_capability_action",
                db=db
            )

    assert decision.selected_tool_id == f"mcp:{conn_id}:custom_tool"
    assert "Test MCP Server: custom_tool" in decision.selected_tool_name
    assert len(decision.candidate_checks) == 1
    assert decision.candidate_checks[0].is_authorized is True
    assert decision.candidate_checks[0].is_connected is True


async def test_mcp_permission_alias_compatibility():
    """Verifies that execute/discover permission keys satisfy call_tools/list_tools requirements."""
    conn_id = str(uuid.uuid4())
    user_id = "user-123"
    # Legacy permission keys: execute, discover
    conn = make_mcp_connection(conn_id, user_id, "connected", "legacy_tool", "legacy_capability_action", perms=["execute", "discover"])
    db = make_mock_db([conn])

    with patch("app.selection.engine.decrypt_secret", return_value='{"server_url": "http://localhost:8085/mcp"}'):
        with patch("app.tools.adapters.mcp_client.mcp_client.health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = (True, {"message": "Healthy"})
            engine = ToolSelectionEngine()
            decision = await engine.evaluate_candidates(
                user_id=user_id,
                capability_id="legacy_capability_action",
                db=db
            )

    assert decision.selected_tool_id == f"mcp:{conn_id}:legacy_tool"
    assert decision.candidate_checks[0].is_authorized is True


async def test_mcp_connection_ownership_enforcement():
    """Verifies that MCP tools belonging to another user are never selected."""
    conn_id = str(uuid.uuid4())
    owner_user_id = "owner-999"
    caller_user_id = "caller-111"
    
    conn = make_mcp_connection(conn_id, owner_user_id, "connected", "private_tool", "private_capability_action")
    db = make_mock_db([conn])  # Returns conn with owner_user_id

    engine = ToolSelectionEngine()
    decision = await engine.evaluate_candidates(
        user_id=caller_user_id,
        capability_id="private_capability_action",
        db=db
    )

    assert decision.selected_tool_id is None
    check = next((c for c in decision.candidate_checks if c.tool_id == f"mcp:{conn_id}:private_tool"), None)
    if check:
        assert check.is_connected is False


async def test_mcp_disconnected_server_disqualifies_tool():
    """Verifies that an MCP tool on a disconnected or coming_soon server is ruled out."""
    conn_id = str(uuid.uuid4())
    user_id = "user-123"
    conn = make_mcp_connection(conn_id, user_id, "not_connected", "unavail_tool", "unavail_capability_action")
    db = make_mock_db([conn])

    engine = ToolSelectionEngine()
    decision = await engine.evaluate_candidates(
        user_id=user_id,
        capability_id="unavail_capability_action",
        db=db
    )

    assert decision.selected_tool_id is None
    assert len(decision.candidate_checks) >= 1
    assert decision.candidate_checks[0].is_connected is False
