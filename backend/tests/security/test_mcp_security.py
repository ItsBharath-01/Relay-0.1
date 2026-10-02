import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.tools.adapters.mcp_client import validate_mcp_config, parse_mcp_config, MCPClient

@pytest.mark.security
def test_user_cannot_register_arbitrary_stdio_command():
    """P0-2: User API must reject arbitrary stdio commands/arguments/env."""
    config = {
        "transport": "stdio",
        "command": "cmd.exe",
        "args": ["/c", "whoami"],
        "is_trusted_operator": False
    }
    with pytest.raises(ValueError, match="Stdio transport is restricted to operator-configured servers"):
        validate_mcp_config(config)


@pytest.mark.security
def test_trusted_operator_stdio_allowed():
    """P0-2: Stdio is allowed if configured via RELAY_TRUSTED_MCP_SERVERS and marked trusted."""
    trusted_cfg = [
        {"id": "local_notes", "command": "python", "args": ["tests/mcp_test_server.py"]}
    ]
    with patch("app.tools.adapters.mcp_client.settings.RELAY_TRUSTED_MCP_SERVERS", str(trusted_cfg)):
        config = {
            "transport": "stdio",
            "server_id": "local_notes",
            "is_trusted_operator": True,
            "command": "python",
            "args": ["tests/mcp_test_server.py"]
        }
        # Should not raise
        validate_mcp_config(config)


@pytest.mark.security
def test_mcp_session_key_includes_user_and_connection():
    """P0-2: Session manager keys must isolate sessions by (user_id, connection_id)."""
    client = MCPClient()
    
    cfg_user1 = {
        "transport": "streamable_http",
        "server_url": "http://127.0.0.1:8085/mcp",
        "user_id": "user-1",
        "connection_id": "conn-1"
    }
    cfg_user2 = {
        "transport": "streamable_http",
        "server_url": "http://127.0.0.1:8085/mcp",
        "user_id": "user-2",
        "connection_id": "conn-2"
    }
    
    from app.tools.adapters.mcp_client import _get_session_key
    key1 = _get_session_key(cfg_user1)
    key2 = _get_session_key(cfg_user2)
    
    assert key1 != key2
    assert "user-1" in key1
    assert "user-2" in key2
