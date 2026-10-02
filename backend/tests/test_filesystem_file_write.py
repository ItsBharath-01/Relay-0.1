"""
test_filesystem_file_write.py — Regression tests for Local Filesystem file_write capability.

Verifies:
1. Local Filesystem exposes file_read.
2. Local Filesystem exposes file_write.
3. file_write selects Local Filesystem when authorized/connected.
4. file_write is blocked when Local Filesystem is disconnected (when requires_connection is set)
   or unavailable.
5. Writes outside the sandbox remain blocked (path traversal, absolute paths).
6. Overwrite protection behaves properly (error on existing file unless overwrite=True).
7. Independent read-back verification passes on write and fails on mismatch.
8. Risk classification correctly marks file_write as write mutating state.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.adapters.filesystem import LocalFilesystemTool
from app.tools.registry.base import ExecutionContext, EffectClass
from app.tools.registry import get_tool, get_tools_for_capability
from app.tools.registry.capabilities import get_capability
from app.selection.engine import ToolSelectionEngine
from app.risk.classifier import risk_classifier
from app.models.entities import Connection, Permission


def make_mock_db(connections: list) -> AsyncMock:
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = connections
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("RELAY_WORKSPACE_ROOT", str(workspace))
    return workspace


# ── Test 1: Local Filesystem exposes file_read ─────────────────────────────────

def test_filesystem_exposes_file_read():
    tool = LocalFilesystemTool()
    assert "file_read" in tool.provides
    actions = {a.action: a for a in tool.describe_actions()}
    assert "file_read" in actions
    assert actions["file_read"].capability_id == "file_read"
    assert actions["file_read"].effect_class == EffectClass.READ_ONLY


# ── Test 2: Local Filesystem exposes file_write ────────────────────────────────

def test_filesystem_exposes_file_write():
    tool = LocalFilesystemTool()
    assert "file_write" in tool.provides
    actions = {a.action: a for a in tool.describe_actions()}
    assert "file_write" in actions
    assert actions["file_write"].capability_id == "file_write"
    assert actions["file_write"].effect_class == EffectClass.NON_IDEMPOTENT_WRITE

    # Capability registry verification
    cap = get_capability("file_write")
    assert cap is not None
    assert cap.id == "file_write"
    assert cap.default_risk == "medium"

    # Tool registry mapping verification
    tools_for_cap = get_tools_for_capability("file_write")
    assert any(t.id == "local_filesystem" for t in tools_for_cap)


# ── Test 3: file_write selects Local Filesystem when authorized ────────────────

@pytest.mark.asyncio
async def test_file_write_selects_local_filesystem():
    engine = ToolSelectionEngine()
    db = make_mock_db([])

    with patch("app.tools.adapters.filesystem.LocalFilesystemTool.health_check", new_callable=AsyncMock) as mock_hc:
        mock_hc.return_value = (True, "Filesystem ready at /workspace")
        record = await engine.evaluate_candidates(
            user_id="user-test-fs",
            capability_id="file_write",
            db=db,
        )

    assert record.selected_tool_id == "local_filesystem"
    fs_check = next(c for c in record.candidate_checks if c.tool_id == "local_filesystem")
    assert fs_check.is_compatible is True
    assert fs_check.passed_all is True


# ── Test 4: file_write blocked when connection disconnected (if configured) ────

@pytest.mark.asyncio
async def test_file_write_blocked_when_connection_disconnected():
    engine = ToolSelectionEngine()

    # If local_filesystem has a connection requirement, test disconnection behavior
    tool = LocalFilesystemTool()
    with patch.object(tool, "requires_connection", "local_filesystem"):
        with patch("app.selection.engine.get_tools_for_capability", return_value=[tool]):
            # Connection exists but status is 'not_connected'
            conn = Connection(
                id="conn-fs-1",
                user_id="user-1",
                app_id="local_filesystem",
                name="Local Files",
                status="not_connected",
                auth_type="local",
            )
            db = make_mock_db([conn])

            record = await engine.evaluate_candidates(
                user_id="user-1",
                capability_id="file_write",
                db=db,
            )
            assert record.selected_tool_id is None
            fs_check = next(c for c in record.candidate_checks if c.tool_id == "local_filesystem")
            assert fs_check.is_connected is False
            assert fs_check.passed_all is False


# ── Test 5: Writes outside the sandbox remain blocked ──────────────────────────

@pytest.mark.asyncio
async def test_filesystem_write_traversal_blocked(temp_workspace):
    tool = LocalFilesystemTool()
    ctx = ExecutionContext()

    # Dot-dot traversal escape
    res = await tool.execute(
        "file_write",
        {"path": "../../outside.txt", "content": "malicious content"},
        ctx=ctx
    )
    assert res.status == "error"
    assert "Path traversal" in res.error or "outside workspace" in res.error

    # Windows style traversal
    res2 = await tool.execute(
        "file_write",
        {"path": "..\\..\\outside.txt", "content": "malicious content"},
        ctx=ctx
    )
    assert res2.status == "error"


@pytest.mark.asyncio
async def test_filesystem_write_absolute_blocked(temp_workspace):
    tool = LocalFilesystemTool()
    ctx = ExecutionContext()

    res = await tool.execute(
        "file_write",
        {"path": "/etc/shadow", "content": "root:x"},
        ctx=ctx
    )
    assert res.status == "error"
    assert "Path traversal" in res.error or "invalid absolute path" in res.error


# ── Test 6: file_write execution success and overwrite behavior ────────────────

@pytest.mark.asyncio
async def test_filesystem_write_success_and_overwrite(temp_workspace):
    tool = LocalFilesystemTool()
    ctx = ExecutionContext()

    # Write file
    res = await tool.execute(
        "file_write",
        {"path": "notes/todo.txt", "content": "1. Buy milk\n2. Ship Relay"},
        ctx=ctx
    )
    assert res.status == "success"
    written_file = temp_workspace / "notes" / "todo.txt"
    assert written_file.exists()
    assert written_file.read_text(encoding="utf-8") == "1. Buy milk\n2. Ship Relay"

    # Attempt to write existing without overwrite -> must fail
    res_duplicate = await tool.execute(
        "file_write",
        {"path": "notes/todo.txt", "content": "new content", "overwrite": False},
        ctx=ctx
    )
    assert res_duplicate.status == "error"
    assert "already exists" in res_duplicate.error

    # Write with overwrite=True -> must succeed
    res_overwrite = await tool.execute(
        "file_write",
        {"path": "notes/todo.txt", "content": "Updated content", "overwrite": True},
        ctx=ctx
    )
    assert res_overwrite.status == "success"
    assert written_file.read_text(encoding="utf-8") == "Updated content"


# ── Test 7: Independent read-back verification ─────────────────────────────────

@pytest.mark.asyncio
async def test_filesystem_write_independent_verification(temp_workspace):
    tool = LocalFilesystemTool()
    ctx = ExecutionContext()

    # Write valid content
    params = {"path": "report.txt", "content": "Quarterly summary"}
    res = await tool.execute("file_write", params, ctx=ctx)
    assert res.status == "success"

    # Verification should pass
    outcome = await tool.verify("file_write", params, res, ctx=ctx)
    assert outcome.result == "passed"
    assert "independently verified" in outcome.reason

    # Verification with mismatched expectation should fail
    mismatch_params = {"path": "report.txt", "content": "Different expected content"}
    outcome_mismatch = await tool.verify("file_write", mismatch_params, res, ctx=ctx)
    assert outcome_mismatch.result == "failed"


# ── Test 8: Risk assessment classification ─────────────────────────────────────

def test_filesystem_write_risk_classification():
    assessment = risk_classifier.assess_action(
        capability_id="file_write",
        action="file_write",
        params={"path": "out.txt", "content": "data"},
        tool_id="local_filesystem"
    )
    assert assessment.risk_level in ("medium", "high")
    assert assessment.requires_approval is True
