import asyncio
import json
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import Response

from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.models.entities import (
    User,
    Goal,
    Plan,
    Task,
    Execution,
    Connection,
    Permission,
    Verification,
    UserPreference,
    Approval,
)
from app.agent.execution_runner import execution_runner
from app.security.crypto import encrypt_secret


def _uid():
    return uuid.uuid4().hex[:12]


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


@pytest.mark.integration
async def test_runner_filesystem_connector_e2e(tmp_path, monkeypatch):
    """Planner -> Selection -> Runner -> Filesystem Adapter -> Verification -> Completed."""
    tag = _uid()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("RELAY_WORKSPACE_ROOT", str(workspace))
    test_file = workspace / "doc.txt"
    test_file.write_text("Relay workspace file content")

    async with async_session_maker() as db:
        user = User(id=f"u-fs-{tag}", name="FS User", email=f"fs-{tag}@relay.test", hashed_password="pw")
        goal = Goal(id=f"g-fs-{tag}", user_id=user.id, text="Read doc.txt from workspace")
        task = Task(
            id=f"t-fs-{tag}",
            order=1, plan_id=f"p-fs-{tag}",
            title="Read local file",
            capability_id="file_read",
            status="pending",
            action="file_read",
            params={"path": "doc.txt"}
        )
        plan = Plan(id=f"p-fs-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-fs-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, goal, plan, task, execution])
        await db.commit()

    # Run execution directly
    await execution_runner.run_execution(execution.id)

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert "Relay workspace file content" in str(task_db.result)


@pytest.mark.integration
async def test_runner_rest_connector_e2e():
    """Planner -> Selection -> Runner -> REST Adapter -> Verification -> Completed."""
    tag = _uid()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status": "ok", "items": [1, 2]}'
    mock_resp.headers = {"Content-Type": "application/json"}

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async with async_session_maker() as db:
        user = User(id=f"u-rest-{tag}", name="REST User", email=f"rest-{tag}@relay.test", hashed_password="pw")
        conn = Connection(
            id=f"c-rest-{tag}",
            user_id=user.id,
            app_id="rest_connector",
            name="REST Connector",
            status="connected",
            encrypted_credentials=encrypt_secret(json.dumps({"headers": {}}))
        )
        goal = Goal(id=f"g-rest-{tag}", user_id=user.id, text="Call external REST API")
        task = Task(
            id=f"t-rest-{tag}",
            order=1, plan_id=f"p-rest-{tag}",
            title="Fetch external data",
            capability_id="api_request",
            status="pending",
            action="api_request",
            params={"url": "https://api.example.com/items", "method": "GET"}
        )
        plan = Plan(id=f"p-rest-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-rest-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, conn, goal, plan, task, execution])
        await db.commit()

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("app.tools.adapters.rest.RestApiTool._is_safe_url", return_value=True):
        await execution_runner.run_execution(execution.id)

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert task_db.result.get("status_code") == 200


@pytest.mark.integration
async def test_runner_github_connector_e2e():
    """Planner -> Selection -> Runner -> GitHub Adapter -> Verification -> Completed."""
    tag = _uid()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"title": "Test Issue", "state": "open", "body": "Issue description"}
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async with async_session_maker() as db:
        user = User(id=f"u-gh-{tag}", name="GH User", email=f"gh-{tag}@relay.test", hashed_password="pw")
        conn = Connection(
            id=f"c-gh-{tag}",
            user_id=user.id,
            app_id="github",
            name="GitHub Account",
            status="connected",
            encrypted_credentials=encrypt_secret("ghp_fake_token_12345")
        )
        perm = Permission(
            id=f"p-gh-{tag}",
            connection_id=conn.id,
            label="Scope", permission_key="repo",
            is_granted=True
        )
        goal = Goal(id=f"g-gh-{tag}", user_id=user.id, text="Read GitHub issue")
        task = Task(
            id=f"t-gh-{tag}",
            order=1, plan_id=f"p-gh-{tag}",
            title="Read issue #42",
            capability_id="issue_read",
            status="pending",
            action="issue_read",
            params={"repository": "owner/repo", "issue_number": 42}
        )
        plan = Plan(id=f"p-gh-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-gh-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, conn, perm, goal, plan, task, execution])
        await db.commit()

    with patch("httpx.AsyncClient", return_value=mock_client):
        await execution_runner.run_execution(execution.id)

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert task_db.result.get("title") == "Test Issue"


@pytest.mark.integration
async def test_runner_slack_connector_e2e():
    """Planner -> Selection -> Runner -> Slack Adapter -> Verification -> Completed."""
    tag = _uid()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "channel": "C123", "ts": "1234.56"}
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async with async_session_maker() as db:
        user = User(id=f"u-slack-{tag}", name="Slack User", email=f"slack-{tag}@relay.test", hashed_password="pw")
        pref = UserPreference(id=f"pref-slack-{tag}", user_id=user.id, ask_external_messages=False, threshold_people=10)
        conn = Connection(
            id=f"c-slack-{tag}",
            user_id=user.id,
            app_id="slack",
            name="Slack Workspace",
            status="connected",
            encrypted_credentials=encrypt_secret("xoxb-fake-slack-token")
        )
        perm = Permission(
            id=f"p-slack-{tag}",
            connection_id=conn.id,
            label="Scope", permission_key="chat:write",
            is_granted=True
        )
        goal = Goal(id=f"g-slack-{tag}", user_id=user.id, text="Send message to Slack")
        task = Task(
            id=f"t-slack-{tag}",
            order=1, plan_id=f"p-slack-{tag}",
            title="Post to general",
            capability_id="message_send",
            status="pending",
            action="message_send",
            params={"channel": "general", "text": "Deployment finished"}
        )
        plan = Plan(id=f"p-slack-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-slack-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, pref, conn, perm, goal, plan, task, execution])
        await db.commit()

    with patch("httpx.AsyncClient", return_value=mock_client):
        await execution_runner.run_execution(execution.id)

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert task_db.result.get("channel") == "C123"


@pytest.mark.integration
async def test_runner_gmail_connector_e2e():
    """Planner -> Selection -> Runner -> Gmail Adapter -> Verification -> Completed."""
    tag = _uid()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "msg_999",
        "threadId": "thread_888",
        "snippet": "Test email snippet",
        "labelIds": ["SENT"]
    }
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async with async_session_maker() as db:
        user = User(id=f"u-gmail-{tag}", name="Gmail User", email=f"gmail-{tag}@relay.test", hashed_password="pw")
        pref = UserPreference(id=f"pref-gmail-{tag}", user_id=user.id, ask_external_messages=False, threshold_people=10)
        conn = Connection(
            id=f"c-gmail-{tag}",
            user_id=user.id,
            app_id="gmail",
            name="Gmail Account",
            status="connected",
            encrypted_credentials=encrypt_secret(json.dumps({"access_token": "ya29.fake_google_token"}))
        )
        perm_read = Permission(
            id=f"p-gmail-r-{tag}",
            connection_id=conn.id,
            label="Read", permission_key="read",
            is_granted=True
        )
        perm_draft = Permission(
            id=f"p-gmail-d-{tag}",
            connection_id=conn.id,
            label="Draft", permission_key="draft",
            is_granted=True
        )
        perm_send = Permission(
            id=f"p-gmail-s-{tag}",
            connection_id=conn.id,
            label="Send", permission_key="send",
            is_granted=True
        )
        goal = Goal(id=f"g-gmail-{tag}", user_id=user.id, text="Send an email")
        task = Task(
            id=f"t-gmail-{tag}",
            order=1, plan_id=f"p-gmail-{tag}",
            title="Send notification email",
            capability_id="email_send",
            status="pending",
            action="email_send",
            params={"to": "client@example.com", "subject": "Update", "body": "All systems operational"}
        )
        plan = Plan(id=f"p-gmail-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-gmail-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, pref, conn, perm_read, perm_draft, perm_send, goal, plan, task, execution])
        await db.commit()

    with patch("app.tools.adapters.gmail.httpx.AsyncClient", return_value=mock_client):
        await execution_runner.run_execution(execution.id)

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert task_db.result.get("message_id") == "msg_999"


@pytest.mark.integration
async def test_runner_google_calendar_connector_e2e():
    """Planner -> Selection -> Runner -> Calendar Adapter -> Verification -> Completed."""
    tag = _uid()

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": "cal_event_123",
        "htmlLink": "https://calendar.google.com/event?id=123",
        "summary": "Team Sync",
        "created": "2026-10-02T10:00:00Z",
        "status": "confirmed"
    }
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    # Re-fetch for verification
    ver_resp = MagicMock()
    ver_resp.status_code = 200
    ver_resp.json.return_value = mock_resp.json.return_value
    mock_client.get = AsyncMock(return_value=ver_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async with async_session_maker() as db:
        user = User(id=f"u-cal-{tag}", name="Cal User", email=f"cal-{tag}@relay.test", hashed_password="pw")
        conn = Connection(
            id=f"c-cal-{tag}",
            user_id=user.id,
            app_id="google_calendar",
            name="Google Calendar",
            status="connected",
            encrypted_credentials=encrypt_secret(json.dumps({"access_token": "ya29.fake_cal_token"}))
        )
        perm_read = Permission(
            id=f"p-cal-r-{tag}",
            connection_id=conn.id,
            label="Read", permission_key="read",
            is_granted=True
        )
        perm_create = Permission(
            id=f"p-cal-c-{tag}",
            connection_id=conn.id,
            label="Create", permission_key="create",
            is_granted=True
        )
        goal = Goal(id=f"g-cal-{tag}", user_id=user.id, text="Schedule a team meeting")
        task = Task(
            id=f"t-cal-{tag}",
            order=1, plan_id=f"p-cal-{tag}",
            title="Create meeting event",
            capability_id="calendar_create",
            status="pending",
            action="calendar_create",
            params={"summary": "Team Sync", "start_time": "2026-10-02T14:00:00Z", "end_time": "2026-10-02T15:00:00Z"}
        )
        plan = Plan(id=f"p-cal-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-cal-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, conn, perm_read, perm_create, goal, plan, task, execution])
        await db.commit()

    with patch("app.tools.adapters.google_calendar.httpx.AsyncClient", return_value=mock_client):
        await execution_runner.run_execution(execution.id)

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert task_db.result.get("event_id") == "cal_event_123"


@pytest.mark.integration
async def test_runner_mcp_connector_e2e():
    """Planner -> Selection -> Runner -> MCP Adapter -> Verification -> Completed."""
    tag = _uid()

    mock_mcp_result = {
        "status": "success",
        "tool_name": "create_note",
        "raw_text": "Note 'Project Plan' created successfully with id note_456",
        "data": {"id": "note_456", "title": "Project Plan"},
        "content": [{"type": "text", "text": "Note created"}],
        "is_error": False,
        "session_id": "mcp-sess-123"
    }

    async with async_session_maker() as db:
        user = User(id=f"u-mcp-{tag}", name="MCP User", email=f"mcp-{tag}@relay.test", hashed_password="pw")
        conn = Connection(
            id=f"c-mcp-{tag}",
            user_id=user.id,
            app_id="mcp",
            name="MCP Notes",
            status="connected",
            encrypted_credentials=encrypt_secret(json.dumps({"url": "http://127.0.0.1:8085/mcp"}))
        )
        perm_call = Permission(
            id=f"p-mcp-{tag}",
            connection_id=conn.id,
            label="Call Tools", permission_key="call_tools",
            is_granted=True
        )
        goal = Goal(id=f"g-mcp-{tag}", user_id=user.id, text="Create a project plan note")
        task = Task(
            id=f"t-mcp-{tag}",
            order=1, plan_id=f"p-mcp-{tag}",
            title="Create note via MCP",
            capability_id="mcp_call",
            status="pending",
            action="mcp_call",
            params={"tool_name": "create_note", "arguments": {"title": "Project Plan"}}
        )
        plan = Plan(id=f"p-mcp-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-mcp-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, conn, perm_call, goal, plan, task, execution])
        await db.commit()

    async def auto_approve_bg():
        for _ in range(20):
            await asyncio.sleep(0.5)
            async with async_session_maker() as db_inner:
                appr_res = await db_inner.execute(select(Approval).where(Approval.execution_id == execution.id, Approval.status == "pending"))
                appr = appr_res.scalar_one_or_none()
                if appr:
                    appr.status = "approved"
                    await db_inner.commit()
                    break

    bg_task = asyncio.create_task(auto_approve_bg())
    try:
        with patch("app.tools.adapters.mcp_client.mcp_client.call_tool", AsyncMock(return_value=mock_mcp_result)), \
             patch("app.tools.adapters.mcp_adapter.MCPToolAdapter.health_check", AsyncMock(return_value=(True, "Connected"))):
            await execution_runner.run_execution(execution.id)
    finally:
        bg_task.cancel()

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert "note_456" in str(task_db.result)
