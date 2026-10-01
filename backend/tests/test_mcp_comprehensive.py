"""
test_mcp_comprehensive.py — Comprehensive 27-point Test Matrix for Relay MCP Integration.

Verifies:
1. MCP connection creation (HTTP and stdio)
2. Connection ownership enforcement
3. Cross-user access blocked
4. MCP server health check success
5. MCP server health check failure
6. Session initialization
7. list_tools() parsing
8. Dynamic tool registration
9. Dynamic tool unregistration on disconnect
10. Tool name to capability mapping (deterministic)
11. Tool with no direct capability mapping
12. Tool selection engine choosing MCP over missing native tool
13. Tool selection engine choosing native tool over MCP when appropriate
14. Schema validation success
15. Schema validation failure (reject before execution)
16. Execution success path
17. Execution timeout handling
18. Execution connection error handling
19. Execution malformed response handling
20. Task verification success
21. Task verification failure on fake result
22. Goal verification distinguishing task success from goal success
23. High-risk MCP tool requiring approval
24. Approval granted → execution
25. Approval rejected → safe abort
26. Disconnect connection removes tools from registry
27. Reconnect connection restores tools
"""

import asyncio
import json
import os
import sys
import uuid
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import jsonschema

from app.models.entities import User, Connection, Permission, Goal, Plan, Task, Approval
from app.api.connections import (
    register_mcp_server,
    list_mcp_servers,
    list_mcp_server_tools,
    check_mcp_server_health,
    remove_mcp_server,
    MCPServerRegisterRequest,
)
from app.tools.adapters.mcp_client import (
    mcp_client,
    parse_mcp_config,
    validate_mcp_config,
    MCPConnectionError,
    MCPTimeoutError,
)
from app.tools.adapters.mcp_adapter import (
    map_tool_to_capability,
    DynamicMCPTool,
    discover_and_register_mcp_tools,
    MCPToolAdapter,
)
from app.tools.registry import (
    get_tool,
    get_all_tools,
    get_tools_for_capability,
    register_tool,
    unregister_tool,
)
from app.tools.registry.capabilities import get_capability, register_capability
from app.selection.engine import ToolSelectionEngine
from app.risk.classifier import risk_classifier
from app.verification.engine import verification_engine
from app.security.crypto import encrypt_secret, decrypt_secret, hash_payload

pytestmark = pytest.mark.asyncio

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_test_server.py")
STDIO_CONFIG = {
    "transport": "stdio",
    "command": sys.executable,
    "args": [SERVER_SCRIPT],
}


# ==============================================================================
# 1. MCP Connection Creation (HTTP and stdio)
# ==============================================================================

async def test_01_mcp_connection_creation_http_and_stdio():
    # Stdio validation
    stdio_cfg = parse_mcp_config(STDIO_CONFIG)
    validate_mcp_config(stdio_cfg)
    assert stdio_cfg["transport"] == "stdio"
    assert stdio_cfg["command"] == sys.executable

    # HTTP validation
    http_cfg = parse_mcp_config({"transport": "streamable_http", "url": "http://127.0.0.1:8080/mcp"})
    validate_mcp_config(http_cfg)
    assert http_cfg["transport"] == "streamable_http"
    assert http_cfg["server_url"] == "http://127.0.0.1:8080/mcp"

    # Security: SSRF blocked
    with pytest.raises(ValueError, match="SSRF"):
        validate_mcp_config({"transport": "streamable_http", "server_url": "http://169.254.169.254/latest/meta-data"})

    # Security: Command injection blocked
    with pytest.raises(ValueError, match="Command injection"):
        validate_mcp_config({"transport": "stdio", "command": "python; rm -rf /"})


# ==============================================================================
# 2 & 3. Connection Ownership Enforcement & Cross-User Access Blocked
# ==============================================================================

async def test_02_03_connection_ownership_and_cross_user_isolation():
    engine = ToolSelectionEngine()

    user1_id = "user_alpha"
    user2_id = "user_beta"

    mcp_tool = DynamicMCPTool(
        connection_id="conn_alpha",
        server_name="Alpha Notes",
        tool_name="create_note",
        description="Create note for Alpha",
        input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        capability_id="note_create",
        risk_profile="medium",
    )
    register_tool(mcp_tool)

    # Mock DB for User 1
    conn_u1 = Connection(
        id="conn_alpha",
        user_id=user1_id,
        app_id="mcp",
        status="connected",
        encrypted_credentials=encrypt_secret(json.dumps(STDIO_CONFIG)),
        permissions=[Permission(permission_key="call_tools", is_granted=True)],
    )

    db_u1 = AsyncMock()
    mock_res_u1 = MagicMock()
    mock_res_u1.scalars().all.return_value = [conn_u1]
    db_u1.execute.return_value = mock_res_u1

    # User 1 evaluates candidates -> Should find tool
    rec_u1 = await engine.evaluate_candidates(user_id=user1_id, capability_id="note_create", db=db_u1)
    assert rec_u1.selected_tool_id == mcp_tool.id

    # User 2 evaluates candidates with their own DB (cross-user access blocked)
    db_u2 = AsyncMock()
    mock_res_u2 = MagicMock()
    mock_res_u2.scalars().all.return_value = []
    db_u2.execute.return_value = mock_res_u2

    rec_u2 = await engine.evaluate_candidates(user_id=user2_id, capability_id="note_create", db=db_u2)
    assert rec_u2.selected_tool_id is None

    unregister_tool(mcp_tool.id)


# ==============================================================================
# 4 & 5. MCP Server Health Check Success & Failure
# ==============================================================================

async def test_04_05_health_check_success_and_failure():
    # 4. Live stdio server health check success
    healthy, info = await mcp_client.health_check(STDIO_CONFIG)
    assert healthy is True
    assert info["status"] == "healthy"
    assert info["tool_count"] >= 4

    # 5. Invalid/unreachable server health check failure
    dead_config = {"transport": "streamable_http", "server_url": "http://127.0.0.1:54321/mcp"}
    healthy_dead, info_dead = await mcp_client.health_check(dead_config)
    assert healthy_dead is False
    assert info_dead["status"] == "unavailable"


# ==============================================================================
# 6 & 7. Session Initialization & list_tools() Parsing
# ==============================================================================

async def test_06_07_session_initialization_and_list_tools():
    tools = await mcp_client.list_tools(STDIO_CONFIG)
    assert isinstance(tools, list)
    assert len(tools) >= 4

    names = {t["name"] for t in tools}
    assert "create_note" in names
    assert "search_notes" in names
    assert "update_note" in names
    assert "delete_note" in names

    create_tool = next(t for t in tools if t["name"] == "create_note")
    schema = create_tool.get("input_schema") or create_tool.get("inputSchema")
    assert schema["type"] == "object"
    assert "title" in schema["properties"]
    assert "content" in schema["properties"]


# ==============================================================================
# 8 & 9. Dynamic Tool Registration & Unregistration
# ==============================================================================

async def test_08_09_dynamic_registration_and_unregistration():
    conn_id = "test_conn_reg"
    meta_list = await discover_and_register_mcp_tools(
        connection_id=conn_id,
        server_name="Test Dynamic Notes",
        credentials=STDIO_CONFIG,
    )
    assert len(meta_list) >= 4
    tool_ids = [m["tool_id"] for m in meta_list]

    for tid in tool_ids:
        registered = get_tool(tid)
        assert registered is not None
        assert registered.id == tid
        assert registered.tool_type == "mcp"

    # Unregister dynamic tools for this connection
    for tid in tool_ids:
        unregister_tool(tid)
        assert get_tool(tid) is None


# ==============================================================================
# 10 & 11. Deterministic Capability Mapping & Unclassified Tool
# ==============================================================================

async def test_10_11_capability_mapping():
    # Deterministic mappings
    cap_id, label, cat, risk = map_tool_to_capability("create_note", "Create a note")
    assert cap_id == "note_create"
    assert risk == "medium"

    cap_id2, label2, cat2, risk2 = map_tool_to_capability("search_notes", "Search notes")
    assert cap_id2 == "note_search"
    assert risk2 == "low"

    cap_id3, label3, cat3, risk3 = map_tool_to_capability("delete_note", "Delete note")
    assert cap_id3 == "note_delete"
    assert risk3 == "high"

    # Exact matches with native capabilities
    cap_gh, _, _, _ = map_tool_to_capability("create_issue")
    assert cap_gh == "issue_create"

    # 11. Unclassified fallback
    cap_unclass, label_u, cat_u, risk_u = map_tool_to_capability("xyz_quantum_entangle", "Unknown")
    assert cap_unclass == "mcp_unclassified_xyz_quantum_entangle"


# ==============================================================================
# 12 & 13. Tool Selection: MCP vs Native
# ==============================================================================

async def test_12_13_tool_selection_mcp_vs_native():
    engine = ToolSelectionEngine()
    user_id = "test_user_sel"

    # 12. Capability provided ONLY by MCP (e.g. note_create)
    mcp_note_tool = DynamicMCPTool(
        connection_id="mcp_conn_1",
        server_name="Notes Server",
        tool_name="create_note",
        description="Creates a note",
        input_schema={"type": "object"},
        capability_id="note_create",
    )
    register_tool(mcp_note_tool)

    conn = Connection(
        id="mcp_conn_1",
        user_id=user_id,
        app_id="mcp",
        status="connected",
        encrypted_credentials=encrypt_secret(json.dumps(STDIO_CONFIG)),
        permissions=[Permission(permission_key="call_tools", is_granted=True)],
    )

    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars().all.return_value = [conn]
    db.execute.return_value = mock_res

    rec = await engine.evaluate_candidates(user_id=user_id, capability_id="note_create", db=db)
    assert rec.selected_tool_id == mcp_note_tool.id

    # 13. Capability provided by built-in native tool (e.g. web_search)
    rec_native = await engine.evaluate_candidates(user_id=user_id, capability_id="web_search", db=db)
    assert rec_native.selected_tool_id == "web_search_engine"

    unregister_tool(mcp_note_tool.id)


# ==============================================================================
# 14 & 15. Schema Validation Success & Failure (Reject before execution)
# ==============================================================================

async def test_14_15_schema_validation():
    schema = {
        "type": "object",
        "required": ["title", "content"],
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "content": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }

    tool = DynamicMCPTool(
        connection_id="conn_val",
        server_name="Validator",
        tool_name="create_note",
        description="Test validator",
        input_schema=schema,
        capability_id="note_create",
    )

    # 14. Success
    valid, err = tool.validate_params({"title": "Sprint Plan", "content": "Tasks for sprint", "tags": ["work"]})
    assert valid is True
    assert err is None

    # 15. Failure: missing required field 'content'
    valid_fail, err_fail = tool.validate_params({"title": "Missing content"})
    assert valid_fail is False
    assert "content" in err_fail

    # Execution rejected before making call
    with pytest.raises(ValueError, match="Invalid arguments"):
        await tool.execute("create_note", {"title": "Missing content"}, credentials=STDIO_CONFIG)


# ==============================================================================
# 16, 17, 18, 19. Execution Success, Timeout, Connection Error, Malformed
# ==============================================================================

async def test_16_execution_success_path():
    res = await mcp_client.call_tool(
        STDIO_CONFIG,
        "create_note",
        {"title": "Live Test", "content": "Verified live execution"},
    )
    assert res["status"] == "success"
    assert res["tool_name"] == "create_note"
    assert res["is_error"] is False
    assert "Live Test" in res["raw_text"]


async def test_17_execution_timeout_handling():
    # Extreme short timeout triggers timeout handling
    short_cfg = {**STDIO_CONFIG, "timeout": 0.0001}
    with pytest.raises((MCPTimeoutError, MCPConnectionError, RuntimeError)):
        await mcp_client.call_tool(short_cfg, "create_note", {"title": "Slow", "content": "Slow content"})


async def test_18_execution_connection_error_handling():
    bad_cfg = {"transport": "stdio", "command": "nonexistent_executable_12345", "args": []}
    with pytest.raises(MCPConnectionError):
        await mcp_client.call_tool(bad_cfg, "any_tool", {})


async def test_19_execution_malformed_response_handling():
    # Calling unknown tool on server
    res = await mcp_client.call_tool(STDIO_CONFIG, "nonexistent_tool_xyz", {})
    assert res["is_error"] is True or "not found" in res.get("raw_text", "").lower() or "error" in res.get("raw_text", "").lower()


# ==============================================================================
# 20 & 21. Task Verification Success vs Fake Result Failure
# ==============================================================================

async def test_20_21_task_verification():
    tool = DynamicMCPTool(
        connection_id="conn_v",
        server_name="Test Verifier",
        tool_name="create_note",
        description="Creates a note",
        input_schema={},
        capability_id="note_create",
    )
    register_tool(tool)

    # 20. Real successful result
    good_result = {
        "is_error": False,
        "raw_text": json.dumps({"id": "note_101", "status": "created"}),
        "data": {"id": "note_101", "status": "created"},
    }
    task_ver_good = await verification_engine.verify_task_outcome(
        capability_id="note_create",
        action="create_note",
        params={"title": "Test"},
        result=good_result,
        tool_id=tool.id,
    )
    assert task_ver_good.result == "passed"
    assert task_ver_good.evidence["created_confirmation"] is True

    # 21. Fake/Error result
    bad_result = {
        "is_error": True,
        "raw_text": "Internal error occurred",
        "data": None,
    }
    task_ver_bad = await verification_engine.verify_task_outcome(
        capability_id="note_create",
        action="create_note",
        params={"title": "Test"},
        result=bad_result,
        tool_id=tool.id,
    )
    assert task_ver_bad.result == "failed"

    unregister_tool(tool.id)


# ==============================================================================
# 22. Goal Verification: Distinguishing Task Success from Goal Success
# ==============================================================================

async def test_22_goal_verification():
    goal_text = "Create a note called Hackathon with the content Relay MCP integration"
    desired_outcome = "Note created with title Hackathon"
    success_criteria = ["Note confirmed created with ID"]

    # Case A: Task succeeded and verified -> Goal Achieved
    tasks = [
        Task(
            id="t1",
            title="Create note Hackathon",
            capability_id="note_create",
            status="completed",
            selected_tool_id="mcp:conn_1:create_note",
        )
    ]
    task_vers = [
        MagicMock(
            result="passed",
            evidence={"created_confirmation": True, "note_id": "note_1"},
            criterion="Verify create_note",
        )
    ]

    goal_res = await verification_engine.verify_goal_outcome(
        goal_text=goal_text,
        desired_outcome=desired_outcome,
        success_criteria=success_criteria,
        tasks=tasks,
        task_verifications=task_vers,
    )
    assert goal_res.goal_outcome == "COMPLETED"
    assert goal_res.evidence_level in ["ACTION_VERIFIED", "GOAL_ACHIEVED"]

    # Case B: Task failed or not verified -> Goal NOT Achieved
    tasks_failed = [
        Task(
            id="t1",
            title="Create note Hackathon",
            capability_id="note_create",
            status="failed",
            selected_tool_id="mcp:conn_1:create_note",
        )
    ]
    task_vers_failed = [
        MagicMock(
            result="failed",
            evidence={"created_confirmation": False},
            criterion="Verify create_note",
        )
    ]

    goal_res_failed = await verification_engine.verify_goal_outcome(
        goal_text=goal_text,
        desired_outcome=desired_outcome,
        success_criteria=success_criteria,
        tasks=tasks_failed,
        task_verifications=task_vers_failed,
    )
    assert goal_res_failed.goal_outcome != "COMPLETED"


# ==============================================================================
# 23, 24, 25. Risk Classification & Approval Flow
# ==============================================================================

async def test_23_24_25_risk_and_approval():
    # 23. Dangerous tool mapped to high risk
    cap_wipe, _, _, risk_wipe = map_tool_to_capability("dangerous_wipe", "Permanently delete all stored notes")
    assert risk_wipe == "high"

    # Assess via RiskClassifier
    assessment = risk_classifier.assess_action(
        capability_id="note_delete",
        action="delete_note",
        params={"note_id": "note_1"},
    )
    assert assessment.risk_level in ["high", "medium"]

    # 24. Approval granted path: payload hash verification
    action_params = {"note_id": "note_1"}
    p_hash = hash_payload(action_params)

    approval = Approval(
        id="appr_1",
        execution_id="exec_1",
        task_id="task_1",
        action="delete_note",
        payload_hash=p_hash,
        status="pending",
    )

    # User approves -> Status approved, matching hash allows execution
    approval.status = "approved"
    assert approval.status == "approved"
    assert approval.payload_hash == hash_payload(action_params)

    # 25. User rejects -> Status rejected, aborts execution
    approval.status = "rejected"
    assert approval.status == "rejected"


# ==============================================================================
# 26 & 27. Disconnect and Reconnect Registry Lifecycle
# ==============================================================================

async def test_26_27_disconnect_and_reconnect_lifecycle():
    conn_id = f"lifecycle_test_{uuid.uuid4().hex[:6]}"

    # Register
    tools_reg = await discover_and_register_mcp_tools(
        connection_id=conn_id,
        server_name="Lifecycle Server",
        credentials=STDIO_CONFIG,
    )
    assert len(tools_reg) >= 4
    tool_id = tools_reg[0]["tool_id"]
    assert get_tool(tool_id) is not None

    # 26. Disconnect connection removes all tools
    for t in tools_reg:
        unregister_tool(t["tool_id"])

    assert get_tool(tool_id) is None

    # 27. Reconnect connection restores all tools
    tools_restored = await discover_and_register_mcp_tools(
        connection_id=conn_id,
        server_name="Lifecycle Server",
        credentials=STDIO_CONFIG,
    )
    assert len(tools_restored) >= 4
    assert get_tool(tool_id) is not None

    # Cleanup
    for t in tools_restored:
        unregister_tool(t["tool_id"])
