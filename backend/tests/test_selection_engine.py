"""
test_selection_engine.py — Integration tests for ToolSelectionEngine.

Tests that the engine correctly selects the right tool based on connection status,
permissions, and capability for all P2-3 adapters.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.selection.engine import ToolSelectionEngine, SelectionDecisionRecord
from app.models.entities import Connection

pytestmark = pytest.mark.asyncio


def make_connection(app_id: str, status: str = "connected") -> Connection:
    conn = Connection()
    conn.app_id = app_id
    conn.status = status
    conn.encrypted_credentials = "valid_encrypted_val" if status == "connected" else None
    conn.permissions = []
    return conn


def make_db(connections: list) -> AsyncMock:
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = connections
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


async def test_github_issue_create_selected_when_connected():
    engine = ToolSelectionEngine()
    github_conn = make_connection("github", "connected")
    db = make_db([github_conn])

    with patch("app.selection.engine.decrypt_secret", return_value='{"access_token": "token"}'):
        with patch("app.tools.adapters.github.GitHubTool.health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = (True, "Connected to GitHub.")
            record = await engine.evaluate_candidates(
                user_id="user-1",
                capability_id="issue_create",
                db=db,
            )

    assert record.selected_tool_id == "github", f"Expected github, got {record.selected_tool_id}"
    assert record.selected_tool_name == "GitHub API"
    github_check = next(c for c in record.candidate_checks if c.tool_id == "github")
    assert github_check.passed_all is True
    assert github_check.is_connected is True


async def test_github_not_selected_when_disconnected():
    engine = ToolSelectionEngine()
    github_conn = make_connection("github", "not_connected")
    db = make_db([github_conn])

    record = await engine.evaluate_candidates(
        user_id="user-1",
        capability_id="issue_create",
        db=db,
    )

    assert record.selected_tool_id is None
    github_check = next((c for c in record.candidate_checks if c.tool_id == "github"), None)
    if github_check:
        assert github_check.is_connected is False
        assert github_check.passed_all is False


async def test_slack_message_send_selected_when_connected():
    engine = ToolSelectionEngine()
    slack_conn = make_connection("slack", "connected")
    db = make_db([slack_conn])

    with patch("app.selection.engine.decrypt_secret", return_value='{"access_token": "xoxb-test"}'):
        with patch("app.tools.adapters.slack.SlackTool.health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = (True, "Connected to Slack.")
            record = await engine.evaluate_candidates(
                user_id="user-1",
                capability_id="message_send",
                db=db,
            )

    assert record.selected_tool_id == "slack"
    slack_check = next(c for c in record.candidate_checks if c.tool_id == "slack")
    assert slack_check.passed_all is True


async def test_filesystem_file_read_selected_no_connection_required():
    """local_filesystem has requires_connection=None — always eligible."""
    engine = ToolSelectionEngine()
    db = make_db([])  # No connections in DB

    with patch("app.tools.adapters.filesystem.LocalFilesystemTool.health_check", new_callable=AsyncMock) as mock_hc:
        mock_hc.return_value = (True, "Filesystem ready.")
        record = await engine.evaluate_candidates(
            user_id="user-1",
            capability_id="file_read",
            db=db,
        )

    assert record.selected_tool_id == "local_filesystem"
    fs_check = next(c for c in record.candidate_checks if c.tool_id == "local_filesystem")
    assert fs_check.is_connected is True
    assert fs_check.passed_all is True


async def test_rest_api_request_selected_when_connected():
    engine = ToolSelectionEngine()
    rest_conn = make_connection("rest_connector", "connected")
    db = make_db([rest_conn])

    with patch("app.selection.engine.decrypt_secret", return_value='{"access_token": "key"}'):
        with patch("app.tools.adapters.rest.RestApiTool.health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = (True, "REST Connector configured.")
            record = await engine.evaluate_candidates(
                user_id="user-1",
                capability_id="api_request",
                db=db,
            )

    assert record.selected_tool_id == "rest_connector"


async def test_no_tool_returns_none_when_capability_unconnected():
    engine = ToolSelectionEngine()
    db = make_db([])

    record = await engine.evaluate_candidates(
        user_id="user-1",
        capability_id="issue_create",
        db=db,
    )

    assert record.selected_tool_id is None
    assert "No connected" in record.explanation or "Connect" in record.explanation


async def test_excluded_tool_not_selected_in_recovery():
    """Tool excluded in recovery should not be selected even if healthy and connected."""
    engine = ToolSelectionEngine()
    github_conn = make_connection("github", "connected")
    db = make_db([github_conn])

    record = await engine.evaluate_candidates(
        user_id="user-1",
        capability_id="issue_create",
        db=db,
        excluded_tool_ids=["github"],
    )

    assert record.selected_tool_id is None
    excluded = next((c for c in record.candidate_checks if c.tool_id == "github"), None)
    if excluded:
        assert "Excluded" in (excluded.ruled_out_reason or "")


async def test_selection_record_structure():
    engine = ToolSelectionEngine()
    db = make_db([])
    record = await engine.evaluate_candidates(
        user_id="user-1",
        capability_id="web_search",
        db=db,
    )

    assert isinstance(record, SelectionDecisionRecord)
    assert record.capability_id == "web_search"
    assert isinstance(record.candidate_checks, list)
    assert isinstance(record.explanation, str)


async def test_web_search_selected_without_connection():
    """web_search_engine requires no connection — always selected when healthy."""
    engine = ToolSelectionEngine()
    db = make_db([])

    with patch("app.tools.adapters.web_search.WebSearchTool.health_check", new_callable=AsyncMock) as mock_hc:
        mock_hc.return_value = (True, "Web search service is online")
        record = await engine.evaluate_candidates(
            user_id="user-1",
            capability_id="web_search",
            db=db,
        )

    assert record.selected_tool_id == "web_search_engine"
    ws_check = next(c for c in record.candidate_checks if c.tool_id == "web_search_engine")
    assert ws_check.is_connected is True
    assert ws_check.passed_all is True
