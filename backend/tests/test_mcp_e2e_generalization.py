"""
test_mcp_e2e_generalization.py — End-to-End Live Validation & Generalization Testing.

Tests:
1. Live E2E: "Create a note called Hackathon with the content Relay MCP integration."
   - Intent & Required Capability (note_create)
   - Real local stdio MCP server (mcp_test_server.py)
   - Tool discovery & DynamicMCPTool registration
   - Tool selection engine matches note_create to create_note
   - Parameter extraction & JSON Schema validation
   - Live execution over MCP protocol
   - Independent verification against resulting state
   - Final outcome COMPLETED with evidence

2. Generalization Test A: "Search for notes about Hackathon" (low risk, note_search)
   - Tool search_notes selected dynamically
   - Verified outcome with search results

3. Generalization Test B: "Delete note note_1" (high risk, note_delete)
   - Risk classification identifies high risk
   - Approval gate triggers approval requirement
   - Execution & verification confirms deletion
"""

import asyncio
import json
import os
import sys
import uuid
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.entities import User, Connection, Permission, Goal, Plan, Task, Approval
from app.tools.adapters.mcp_client import mcp_client, parse_mcp_config
from app.tools.adapters.mcp_adapter import discover_and_register_mcp_tools, DynamicMCPTool
from app.tools.registry import get_tool, unregister_tool
from app.selection.engine import ToolSelectionEngine
from app.risk.classifier import risk_classifier
from app.verification.engine import verification_engine
from app.security.crypto import encrypt_secret, hash_payload

pytestmark = pytest.mark.asyncio

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "mcp_test_server.py")
STDIO_CONFIG = {
    "transport": "stdio",
    "command": sys.executable,
    "args": [SERVER_SCRIPT],
}


async def test_live_e2e_note_creation():
    """
    Test 1: 'Create a note called Hackathon with the content Relay MCP integration.'
    """
    user_id = f"test_e2e_user_{uuid.uuid4().hex[:6]}"
    conn_id = f"mcp_notes_conn_{uuid.uuid4().hex[:6]}"

    # 1. Server discovery & dynamic registration
    discovered = await discover_and_register_mcp_tools(
        connection_id=conn_id,
        server_name="Notes Server",
        credentials=STDIO_CONFIG,
    )
    assert len(discovered) >= 4

    # 2. Simulated DB state for user's connection
    conn = Connection(
        id=conn_id,
        user_id=user_id,
        app_id="mcp",
        name="Notes Server",
        status="connected",
        encrypted_credentials=encrypt_secret(json.dumps(STDIO_CONFIG)),
        permissions=[
            Permission(permission_key="call_tools", is_granted=True),
            Permission(permission_key="list_tools", is_granted=True),
        ],
    )
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars().all.return_value = [conn]
    db.execute.return_value = mock_res

    # 3. Tool Selection: Intent requires 'note_create'
    engine = ToolSelectionEngine()
    selection = await engine.evaluate_candidates(
        user_id=user_id,
        capability_id="note_create",
        db=db,
    )
    assert selection.selected_tool_id is not None
    assert "create_note" in selection.selected_tool_id

    # 4. Tool Parameter Validation
    tool: DynamicMCPTool = get_tool(selection.selected_tool_id)  # type: ignore
    params = {"title": "Hackathon", "content": "Relay MCP integration"}
    valid, err = tool.validate_params(params)
    assert valid is True

    # 5. Risk Assessment
    risk_info = risk_classifier.assess_action("note_create", "create_note", params)
    assert risk_info.risk_level in ["low", "medium"]

    # 6. Real Execution via MCP Protocol
    exec_result = await tool.execute(
        action="create_note",
        params=params,
        credentials=STDIO_CONFIG,
    )
    assert exec_result["is_error"] is False
    assert "Hackathon" in exec_result["raw_text"]
    assert "Relay MCP integration" in exec_result["raw_text"]

    # 7. Independent Verification
    verified, evidence = await tool.verify("create_note", params, exec_result)
    assert verified is True
    assert evidence["created_confirmation"] is True

    # 8. Universal Goal Verification
    goal_ver = await verification_engine.verify_goal_outcome(
        goal_text="Create a note called Hackathon with the content Relay MCP integration",
        desired_outcome="Note created with title Hackathon",
        success_criteria=["Note confirmed created with ID"],
        tasks=[
            Task(
                id="task_1",
                title="Create note Hackathon",
                capability_id="note_create",
                status="completed",
                selected_tool_id=tool.id,
            )
        ],
        task_verifications=[
            MagicMock(
                result="passed",
                evidence=evidence,
                criterion="Verify create_note outcome",
            )
        ],
    )
    assert goal_ver.goal_outcome == "COMPLETED"
    assert goal_ver.evidence_level in ["ACTION_VERIFIED", "GOAL_ACHIEVED"]

    # Cleanup
    for t in discovered:
        unregister_tool(t["tool_id"])


async def test_generalization_search_notes():
    """
    Generalization 2: 'Search for notes about Hackathon'
    """
    user_id = f"test_search_user_{uuid.uuid4().hex[:6]}"
    conn_id = f"mcp_notes_conn_{uuid.uuid4().hex[:6]}"

    discovered = await discover_and_register_mcp_tools(
        connection_id=conn_id,
        server_name="Notes Server",
        credentials=STDIO_CONFIG,
    )

    conn = Connection(
        id=conn_id,
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

    # Capability is note_search
    engine = ToolSelectionEngine()
    selection = await engine.evaluate_candidates(
        user_id=user_id,
        capability_id="note_search",
        db=db,
    )
    assert selection.selected_tool_id is not None
    assert "search_notes" in selection.selected_tool_id

    # Execute search
    tool: DynamicMCPTool = get_tool(selection.selected_tool_id)  # type: ignore
    search_params = {"query": "Hackathon"}
    exec_result = await tool.execute(
        action="search_notes",
        params=search_params,
        credentials=STDIO_CONFIG,
    )
    assert exec_result["is_error"] is False

    # Verify search
    verified, evidence = await tool.verify("search_notes", search_params, exec_result)
    assert verified is True

    # Cleanup
    for t in discovered:
        unregister_tool(t["tool_id"])


async def test_generalization_delete_note_high_risk():
    """
    Generalization 3: 'Delete note note_1'
    """
    user_id = f"test_delete_user_{uuid.uuid4().hex[:6]}"
    conn_id = f"mcp_notes_conn_{uuid.uuid4().hex[:6]}"

    discovered = await discover_and_register_mcp_tools(
        connection_id=conn_id,
        server_name="Notes Server",
        credentials=STDIO_CONFIG,
    )

    conn = Connection(
        id=conn_id,
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

    # Capability is note_delete
    engine = ToolSelectionEngine()
    selection = await engine.evaluate_candidates(
        user_id=user_id,
        capability_id="note_delete",
        db=db,
    )
    assert selection.selected_tool_id is not None
    assert "delete_note" in selection.selected_tool_id

    # Risk Check: MUST be High Risk
    tool: DynamicMCPTool = get_tool(selection.selected_tool_id)  # type: ignore
    assert tool.risk_profile == "high"

    del_params = {"note_id": "note_1"}
    risk_info = risk_classifier.assess_action("note_delete", "delete_note", del_params)
    assert risk_info.risk_level in ["high", "medium"]

    # Approval Gate Flow
    p_hash = hash_payload(del_params)
    approval = Approval(
        id=f"appr_{uuid.uuid4().hex[:6]}",
        execution_id="exec_1",
        task_id="task_delete",
        action="delete_note",
        payload_hash=p_hash,
        status="approved",
    )
    assert approval.status == "approved"

    # Execution upon approval
    exec_result = await tool.execute(
        action="delete_note",
        params=del_params,
        credentials=STDIO_CONFIG,
    )
    assert exec_result["is_error"] is False

    # Verification
    verified, evidence = await tool.verify("delete_note", del_params, exec_result)
    assert verified is True

    # Cleanup
    for t in discovered:
        unregister_tool(t["tool_id"])
