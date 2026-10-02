import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.api.connections import (
    register_mcp_server,
    list_mcp_servers,
    list_mcp_server_tools,
    check_mcp_server_health,
    remove_mcp_server,
    MCPServerRegisterRequest
)
from app.models.entities import User, Connection, Permission

pytestmark = pytest.mark.asyncio

@patch("app.api.connections._MCPAdapter.health_check", new_callable=AsyncMock)
async def test_register_mcp_server(mock_health):
    mock_health.return_value = (True, "OK")
    
    mock_db = AsyncMock()
    mock_user = User(id="user_123")
    
    # Mock existing connection check (returns None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    
    req = MCPServerRegisterRequest(name="Test MCP", url="http://localhost:8080/mcp")
    
    res = await register_mcp_server(req, current_user=mock_user, db=mock_db)
    
    assert res["name"] == "Test MCP"
    assert res["status"] == "connected"
    assert res["app_id"] == "mcp"
    assert mock_db.add.call_count == 3  # 1 Connection, 2 Permissions

@patch("app.api.connections._MCPAdapter.health_check", new_callable=AsyncMock)
async def test_register_mcp_server_update_existing(mock_health):
    mock_health.return_value = (True, "OK")
    
    mock_db = AsyncMock()
    mock_user = User(id="user_123")
    
    existing_conn = Connection(id="conn_1", app_id="mcp", status="error")
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_conn
    mock_db.execute.return_value = mock_result
    
    req = MCPServerRegisterRequest(name="Updated MCP", url="http://127.0.0.1:8080/mcp")
    
    res = await register_mcp_server(req, current_user=mock_user, db=mock_db)
    
    assert res["name"] == "Updated MCP"
    assert res["status"] == "connected"
    assert existing_conn.name == "Updated MCP"
    assert mock_db.add.call_count == 0  # Should just update

async def test_list_mcp_servers():
    mock_db = AsyncMock()
    mock_user = User(id="user_123")
    
    conn = Connection(
        id="conn_1", app_id="mcp", name="Test", status="connected",
        encrypted_credentials=b"encrypted", permissions=[]
    )
    
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [conn]
    mock_db.execute.return_value = mock_result
    
    servers = await list_mcp_servers(current_user=mock_user, db=mock_db)
    
    assert len(servers) == 1
    assert servers[0]["name"] == "Test"
    assert servers[0]["app_id"] == "mcp"
    assert servers[0]["has_credentials"] is True

@patch("app.api.connections._MCPAdapter.list_tools", new_callable=AsyncMock)
async def test_mcp_list_tools(mock_list):
    mock_list.return_value = [{"name": "tool_1"}]
    
    mock_db = AsyncMock()
    mock_user = User(id="user_123")
    
    conn = Connection(
        id="conn_1", app_id="mcp", name="Test", status="connected",
        encrypted_credentials=b"encrypted",
        permissions=[Permission(permission_key="list_tools", is_granted=True)]
    )
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = conn
    mock_db.execute.return_value = mock_result
    
    with patch("app.api.connections.decrypt_secret", return_value="http://localhost:8080/mcp"):
        res = await list_mcp_server_tools(connection_id="conn_1", current_user=mock_user, db=mock_db)
        
        assert res["tool_count"] == 1
        assert res["tools"][0]["name"] == "tool_1"
