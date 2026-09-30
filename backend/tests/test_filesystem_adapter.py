import app.tools.registry
import os
import pytest
from app.tools.adapters.filesystem import LocalFilesystemTool

pytestmark = pytest.mark.asyncio

@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("RELAY_WORKSPACE_ROOT", str(workspace))
    return workspace

async def test_filesystem_read_success(temp_workspace):
    test_file = temp_workspace / "test.txt"
    test_file.write_text("hello world")
    
    tool = LocalFilesystemTool()
    res = await tool.execute("file_read", {"path": "test.txt"})
    
    assert res.get("content") == "hello world"
    assert res.get("truncated") is False

async def test_filesystem_read_traversal_blocked(temp_workspace):
    tool = LocalFilesystemTool()
    res = await tool.execute("file_read", {"path": "../../../windows/system32/cmd.exe"})
    assert "error" in res
    assert "Path traversal" in res["error"]

async def test_filesystem_read_absolute_blocked(temp_workspace):
    tool = LocalFilesystemTool()
    # Absolute path that isn't inside workspace root
    res = await tool.execute("file_read", {"path": "/etc/passwd"})
    assert "error" in res
    assert "Path traversal" in res["error"]
