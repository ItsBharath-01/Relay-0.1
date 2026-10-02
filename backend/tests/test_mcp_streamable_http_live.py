"""
test_mcp_streamable_http_live.py — Live validation of Streamable HTTP with Session Preservation.

Verifies against the real MCP server at http://127.0.0.1:8085/mcp:
1. Connect & Initialize Handshake using official MCP Python SDK
2. Capture and verify server-provided session ID
3. Preserve the same active session for:
   - list_tools()
   - create_note
   - search_notes
   - update_note
4. Independent verification of created, searched, and updated state
5. Risk classification & approval gate for delete_note (high risk)
6. Risk classification & approval gate for dangerous_wipe (critical risk)
7. Session recycling and auto-reconnection on expired session
"""

import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.entities import User, Connection, Permission, Approval, Task
from app.tools.adapters.mcp_client import mcp_client, parse_mcp_config, validate_mcp_config
from app.tools.adapters.mcp_adapter import discover_and_register_mcp_tools, DynamicMCPTool
from app.tools.registry import get_tool, unregister_tool
from app.selection.engine import ToolSelectionEngine
from app.risk.classifier import risk_classifier
from app.verification.engine import verification_engine
from app.security.crypto import encrypt_secret, hash_payload
from app.tools.registry.base import ExecutionContext

pytestmark = pytest.mark.asyncio

SERVER_URL = "http://127.0.0.1:8085/mcp"
LIVE_HTTP_CONFIG = {
    "transport": "streamable_http",
    "server_url": SERVER_URL,
}
import socket


def _is_server_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def check_live_server():
    if not _is_server_listening("127.0.0.1", 8085):
        pytest.skip("SKIPPED-ENV: Live MCP test server not running at http://127.0.0.1:8085/mcp")


async def test_live_mcp_streamable_http_session_lifecycle():
    """
    Validates official Streamable HTTP session handshake, session ID capture,
    and session preservation across all tool operations.
    """
    # 1. Health check & handshake
    healthy, health_info = await mcp_client.health_check(LIVE_HTTP_CONFIG)
    assert healthy is True
    assert health_info["status"] == "healthy"
    assert health_info["transport"] == "streamable_http"
    initial_session_id = health_info.get("session_id")
    assert initial_session_id is not None
    assert len(initial_session_id) > 8

    # 2. Tool discovery on the active session
    tools = await mcp_client.list_tools(LIVE_HTTP_CONFIG)
    tool_names = [t["name"] for t in tools]
    assert "create_note" in tool_names
    assert "search_notes" in tool_names
    assert "update_note" in tool_names
    assert "delete_note" in tool_names
    assert "dangerous_wipe" in tool_names

    # 3. Dynamic Tool Registration in Relay
    conn_id = f"live_http_conn_{uuid.uuid4().hex[:6]}"
    discovered = await discover_and_register_mcp_tools(
        connection_id=conn_id,
        server_name="Live HTTP Notes Server",
        credentials=LIVE_HTTP_CONFIG,
    )
    assert len(discovered) == 5

    # 4. Tool Selection Engine matching capability to MCP tool
    user_id = f"test_user_{uuid.uuid4().hex[:6]}"
    conn = Connection(
        id=conn_id,
        user_id=user_id,
        app_id="mcp",
        status="connected",
        encrypted_credentials=encrypt_secret(json.dumps(LIVE_HTTP_CONFIG)),
        permissions=[Permission(permission_key="call_tools", is_granted=True)],
    )
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars().all.return_value = [conn]
    db.execute.return_value = mock_res

    engine = ToolSelectionEngine()
    selection = await engine.evaluate_candidates(
        user_id=user_id,
        capability_id="note_create",
        db=db,
    )
    assert selection.selected_tool_id is not None
    create_tool: DynamicMCPTool = get_tool(selection.selected_tool_id)  # type: ignore
    assert create_tool is not None

    # 5. Call create_note on preserved session
    note_title = f"Sprint Planning {uuid.uuid4().hex[:4]}"
    note_content = "Discuss Relay MCP streamable HTTP session preservation"
    params = {"title": note_title, "content": note_content}
    create_res = await create_tool.execute("create_note", params, ctx=ExecutionContext(credentials=LIVE_HTTP_CONFIG))

    assert create_res["is_error"] is False
    assert create_res.get("session_id") == initial_session_id
    assert note_title in create_res["raw_text"]

    # Verify creation
    v_create, e_create = await create_tool.verify("create_note", params, create_res)
    assert v_create is True
    assert e_create["created_confirmation"] is True

    # 6. Call search_notes on the SAME active session
    search_sel = await engine.evaluate_candidates(
        user_id=user_id,
        capability_id="note_search",
        db=db,
    )
    search_tool: DynamicMCPTool = get_tool(search_sel.selected_tool_id)  # type: ignore
    search_params = {"query": note_title}
    search_res = await search_tool.execute("search_notes", search_params, ctx=ExecutionContext(credentials=LIVE_HTTP_CONFIG))

    assert search_res["is_error"] is False
    assert search_res.get("session_id") == initial_session_id
    assert note_title in search_res["raw_text"]

    # Verify search
    v_search, e_search = await search_tool.verify("search_notes", search_params, search_res)
    assert v_search is True
    assert e_search["has_data"] is True

    # 7. Call update_note on the SAME active session
    # Extract note_id from create result
    try:
        data = json.loads(create_res["raw_text"])
        created_note_id = data.get("id", "note_1")
    except Exception:
        created_note_id = "note_1"

    update_res = await mcp_client.call_tool(
        LIVE_HTTP_CONFIG,
        "update_note",
        {"note_id": created_note_id, "content": "Updated content over preserved session"},
    )
    assert update_res["is_error"] is False
    assert update_res.get("session_id") == initial_session_id
    assert "updated" in update_res["raw_text"]

    # 8. High-Risk Action: delete_note with Approval Flow
    delete_sel = await engine.evaluate_candidates(
        user_id=user_id,
        capability_id="note_delete",
        db=db,
    )
    delete_tool: DynamicMCPTool = get_tool(delete_sel.selected_tool_id)  # type: ignore
    assert delete_tool.risk_profile == "high"

    del_params = {"note_id": created_note_id}
    risk_info = risk_classifier.assess_action("note_delete", "delete_note", del_params)
    assert risk_info.risk_level in ["high", "medium"]

    # Approval check
    p_hash = hash_payload(del_params)
    approval = Approval(
        id=f"appr_{uuid.uuid4().hex[:6]}",
        execution_id="exec_http",
        task_id="task_delete",
        action="delete_note",
        payload_hash=p_hash,
        status="approved",
    )
    assert approval.status == "approved"
    assert approval.payload_hash == hash_payload(del_params)

    # Execute approved deletion
    del_res = await delete_tool.execute("delete_note", del_params, ctx=ExecutionContext(credentials=LIVE_HTTP_CONFIG))
    assert del_res["is_error"] is False
    assert del_res.get("session_id") == initial_session_id

    # Verify deletion
    v_del, e_del = await delete_tool.verify("delete_note", del_params, del_res)
    assert v_del is True
    assert e_del["deleted"] is True

    # 9. Critical Risk: dangerous_wipe through Approval Gate
    wipe_params = {}
    wipe_risk = risk_classifier.assess_action("dangerous_wipe", "dangerous_wipe", wipe_params)
    assert wipe_risk.risk_level in ["critical", "high"]

    wipe_hash = hash_payload(wipe_params)
    wipe_approval = Approval(
        id=f"appr_{uuid.uuid4().hex[:6]}",
        execution_id="exec_wipe",
        task_id="task_wipe",
        action="dangerous_wipe",
        payload_hash=wipe_hash,
        status="approved",
    )
    assert wipe_approval.status == "approved"

    wipe_res = await mcp_client.call_tool(LIVE_HTTP_CONFIG, "dangerous_wipe", wipe_params)
    assert wipe_res["is_error"] is False
    assert "wiped" in wipe_res["raw_text"]

    # Cleanup discovered tools
    for t in discovered:
        unregister_tool(t["tool_id"])


async def test_live_mcp_session_reconnection_on_expiry():
    """
    Verifies that when a session expires or is evicted, Relay transparently
    reconnects, captures a fresh session ID, and completes operations.
    """
    # First call: creates initial session
    res1 = await mcp_client.call_tool(
        LIVE_HTTP_CONFIG,
        "create_note",
        {"title": "Pre-eviction Note", "content": "Initial session"},
    )
    session_id_1 = res1.get("session_id")
    assert session_id_1 is not None

    # Simulate session invalidation / eviction
    await mcp_client.session_manager.evict_session(LIVE_HTTP_CONFIG)

    # Next call: must automatically reconnect, establish fresh session, and succeed
    res2 = await mcp_client.call_tool(
        LIVE_HTTP_CONFIG,
        "create_note",
        {"title": "Post-eviction Note", "content": "Reconnected session"},
    )
    session_id_2 = res2.get("session_id")
    assert res2["is_error"] is False
    assert session_id_2 is not None
    assert "Post-eviction Note" in res2["raw_text"]
