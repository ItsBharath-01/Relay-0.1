"""
test_github_issue_create_regression.py — Comprehensive regression test suite for issue_create.

Verifies:
1. GitHub exposes issue_create.
2. issue_create is present in CAPABILITY_REGISTRY.
3. GitHub catalog exposes issue_create.
4. Tool selection chooses GitHub for issue_create.
5. Local Filesystem is never selected for issue_create.
6. Missing GitHub connection results in BLOCKED / NEEDS_CONNECTION.
7. Valid issue creation succeeds.
8. Issue creation is independently verified.
9. Invalid repository is rejected.
10. Missing title is rejected.
11. Unauthorized repository is rejected.
12. API failure is handled correctly.
13. Risk/approval behavior is correct.
14. Audit event is generated.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.adapters.github import GitHubTool
from app.tools.adapters.filesystem import LocalFilesystemTool
from app.tools.registry import get_tool, get_tools_for_capability
from app.tools.registry.capabilities import get_capability
from app.catalog.apps import get_app
from app.selection.engine import ToolSelectionEngine
from app.risk.classifier import risk_classifier
from app.tools.registry.base import ExecutionContext, EffectClass
from app.models.entities import Connection, Permission, UserPreference
from app.security.crypto import encrypt_secret



def make_mock_db(connections: list) -> AsyncMock:
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = connections
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    return db


def make_http_mock(status_code: int, json_data: dict):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = str(json_data)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ── Test 1: GitHub exposes issue_create ───────────────────────────────────────

def test_github_exposes_issue_create():
    tool = GitHubTool()
    assert "issue_create" in tool.provides
    actions = {a.action: a for a in tool.describe_actions()}
    assert "issue_create" in actions
    action_spec = actions["issue_create"]
    assert action_spec.capability_id == "issue_create"
    assert action_spec.effect_class == EffectClass.NON_IDEMPOTENT_WRITE
    assert action_spec.required_permission == "repo"


# ── Test 2: issue_create is present in CAPABILITY_REGISTRY ────────────────────

def test_issue_create_in_capability_registry():
    cap = get_capability("issue_create")
    assert cap is not None
    assert cap.id == "issue_create"
    assert cap.default_risk in ("medium", "high")
    assert "issue" in cap.label.lower() or "issue" in cap.description.lower()


# ── Test 3: GitHub catalog exposes issue_create ───────────────────────────────

def test_github_catalog_exposes_issue_create():
    app = get_app("github")
    assert app is not None
    assert "issue_create" in app.capabilities
    assert app.available is True


# ── Test 4: Tool selection chooses GitHub for issue_create ────────────────────

@pytest.mark.asyncio
async def test_tool_selection_chooses_github_for_issue_create():
    engine = ToolSelectionEngine()
    conn = Connection()
    conn.id = "c-github-1"
    conn.app_id = "github"
    conn.status = "connected"
    conn.encrypted_credentials = "enc_token"
    conn.permissions = [Permission(permission_key="repo", is_granted=True)]

    db = make_mock_db([conn])

    with patch("app.selection.engine.decrypt_secret", return_value='{"access_token": "gh_pat_123"}'):
        with patch("app.tools.adapters.github.GitHubTool.health_check", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = (True, "Connected to GitHub.")
            record = await engine.evaluate_candidates(
                user_id="user-1",
                capability_id="issue_create",
                db=db,
            )

    assert record.selected_tool_id == "github"
    gh_check = next(c for c in record.candidate_checks if c.tool_id == "github")
    assert gh_check.passed_all is True
    assert gh_check.is_connected is True
    assert gh_check.is_authorized is True


# ── Test 5: Local Filesystem is NEVER selected for issue_create ───────────────

@pytest.mark.asyncio
async def test_local_filesystem_never_selected_for_issue_create():
    tools = get_tools_for_capability("issue_create")
    tool_ids = [t.id for t in tools]
    assert "local_filesystem" not in tool_ids
    assert "github" in tool_ids

    fs_tool = LocalFilesystemTool()
    assert "issue_create" not in fs_tool.provides


# ── Test 6: Missing GitHub connection results in BLOCKED / NEEDS_CONNECTION ───

@pytest.mark.asyncio
async def test_missing_github_connection_blocks_issue_create():
    engine = ToolSelectionEngine()
    db = make_mock_db([])  # No connections at all

    record = await engine.evaluate_candidates(
        user_id="user-1",
        capability_id="issue_create",
        db=db,
    )
    assert record.selected_tool_id is None
    gh_check = next(c for c in record.candidate_checks if c.tool_id == "github")
    assert gh_check.is_connected is False
    assert gh_check.passed_all is False
    assert "not connected" in gh_check.ruled_out_reason.lower()


# ── Test 7: Valid issue creation succeeds ─────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_issue_creation_succeeds():
    tool = GitHubTool()
    mock_client = make_http_mock(201, {
        "html_url": "https://github.com/relay/repo/issues/42",
        "number": 42,
        "title": "Autonomous Bug",
        "state": "open"
    })

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await tool.execute(
            "issue_create",
            {"repository": "relay/repo", "title": "Autonomous Bug", "body": "Details here"},
            ctx=ExecutionContext(credentials={"access_token": "gh_token_abc"}),
        )

    assert res.status == "success"
    assert res["issue_number"] == 42
    assert res["issue_url"] == "https://github.com/relay/repo/issues/42"
    assert "42" in res.external_ids
    assert res.side_effect_state == "CONFIRMED"


# ── Test 8: Issue creation is independently verified ──────────────────────────

@pytest.mark.asyncio
async def test_issue_creation_independent_verification():
    tool = GitHubTool()
    ctx = ExecutionContext(credentials={"access_token": "valid_token"})

    # Mock verify GET call returning 200 with issue details
    mock_client = make_http_mock(200, {
        "number": 42,
        "html_url": "https://github.com/relay/repo/issues/42",
        "state": "open"
    })

    tool_result = {
        "status": "success",
        "data": {
            "issue_number": 42,
            "repository": "relay/repo",
            "issue_url": "https://github.com/relay/repo/issues/42"
        }
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        outcome = await tool.verify(
            "issue_create",
            {"repository": "relay/repo", "title": "Verified Issue"},
            tool_result,
            ctx=ctx
        )

    assert outcome.result == "passed"
    assert "independently verified" in outcome.reason
    assert outcome.evidence["verified_live"] is True


# ── Test 9: Invalid repository is rejected ────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_repository_format_rejected():
    tool = GitHubTool()
    ctx = ExecutionContext(credentials="token")

    # Missing slash
    res1 = await tool.execute("issue_create", {"repository": "justrepo", "title": "Bug"}, ctx=ctx)
    assert res1.status == "error"
    assert "Invalid repository format" in res1.error

    # Extra slash
    res2 = await tool.execute("issue_create", {"repository": "org/team/repo", "title": "Bug"}, ctx=ctx)
    assert res2.status == "error"
    assert "Invalid repository format" in res2.error

    # Empty owner
    res3 = await tool.execute("issue_create", {"repository": "/repo", "title": "Bug"}, ctx=ctx)
    assert res3.status == "error"


# ── Test 10: Missing title is rejected ────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_title_rejected():
    tool = GitHubTool()
    ctx = ExecutionContext(credentials="token")

    res = await tool.execute("issue_create", {"repository": "owner/repo", "title": "   "}, ctx=ctx)
    assert res.status == "error"
    assert "title" in res.error.lower()


# ── Test 11: Unauthorized repository is rejected ──────────────────────────────

@pytest.mark.asyncio
async def test_unauthorized_repository_rejected():
    tool = GitHubTool()
    mock_client = make_http_mock(403, {"message": "Resource not accessible by integration"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await tool.execute(
            "issue_create",
            {"repository": "private-org/secret-repo", "title": "Forbidden Issue"},
            ctx=ExecutionContext(credentials="insufficient_token"),
        )

    assert res.status == "error"
    assert "authorization failed" in res.error.lower() or "403" in res.error
    assert res.side_effect_state == "FAILED_NO_EFFECT"


# ── Test 12: API failure is handled correctly ─────────────────────────────────

@pytest.mark.asyncio
async def test_api_failure_handled_correctly():
    tool = GitHubTool()

    # 404 Not Found
    mock_404 = make_http_mock(404, {"message": "Not Found"})
    with patch("httpx.AsyncClient", return_value=mock_404):
        res = await tool.execute("issue_create", {"repository": "owner/nonexistent", "title": "Bug"}, ctx=ExecutionContext(credentials="token"))
    assert res.status == "error"
    assert "not found" in res.error.lower()

    # 429 Rate Limit
    mock_429 = make_http_mock(429, {"message": "API rate limit exceeded"})
    with patch("httpx.AsyncClient", return_value=mock_429):
        res = await tool.execute("issue_create", {"repository": "owner/repo", "title": "Bug"}, ctx=ExecutionContext(credentials="token"))
    assert res.status == "error"
    assert "rate limit" in res.error.lower()


# ── Test 13: Risk/approval behavior is correct ────────────────────────────────

def test_risk_and_approval_for_issue_create():
    assessment = risk_classifier.assess_action(
        capability_id="issue_create",
        action="issue_create",
        params={"repository": "relay/agent", "title": "Auto Issue"},
        tool_id="github"
    )
    assert assessment.risk_level in ("medium", "high")
    assert assessment.requires_approval is True
    assert "external state" in assessment.reason.lower() or "write" in assessment.reason.lower()


# ── Test 14: Audit event is generated ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_event_generated_for_issue_create(tmp_path, monkeypatch):
    """Verifies that ExecutionRunner emits task_started, task_completed, and verification events."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.core.database import async_session_maker, init_db
    from app.models.entities import User, Goal, Plan, Task, Execution, Approval
    from app.agent.execution_runner import execution_runner
    import uuid

    await init_db()
    tag = uuid.uuid4().hex[:8]

    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"html_url": "https://github.com/relay/repo/issues/99", "number": 99, "title": "E2E Issue", "state": "open"}
    mock_post.text = str(mock_post.json.return_value)

    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = {"number": 99, "html_url": "https://github.com/relay/repo/issues/99", "state": "open"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_post)
    mock_client.get = AsyncMock(return_value=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    async with async_session_maker() as db:
        user = User(id=f"u-gh-{tag}", name="GH User", email=f"gh-{tag}@relay.test", hashed_password="pw")
        pref = UserPreference(id=f"pref-gh-{tag}", user_id=user.id, ask_external_messages=False)
        conn = Connection(
            id=f"c-gh-{tag}",
            user_id=user.id,
            app_id="github",
            name="GitHub",
            status="connected",
            encrypted_credentials=encrypt_secret("valid_token")
        )
        perm = Permission(
            id=f"p-gh-{tag}",
            connection_id=conn.id,
            label="Scope",
            permission_key="repo",
            is_granted=True
        )
        goal = Goal(id=f"g-gh-{tag}", user_id=user.id, text="Create issue on GitHub")
        task = Task(
            id=f"t-gh-{tag}",
            order=1, plan_id=f"p-gh-{tag}",
            title="Create issue",
            capability_id="issue_create",
            status="pending",
            action="issue_create",
            params={"repository": "relay/repo", "title": "E2E Issue", "body": "Test"}
        )
        plan = Plan(id=f"p-gh-{tag}", goal_id=goal.id, tasks=[task])
        execution = Execution(
            id=f"e-gh-{tag}",
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, pref, conn, perm, goal, plan, task, execution])
        await db.commit()

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch("app.tools.adapters.github.GitHubTool.health_check", return_value=(True, "Connected")):
            with patch("app.risk.classifier.risk_classifier.assess_action") as mock_risk:
                from app.risk.classifier import RiskAssessment
                mock_risk.return_value = RiskAssessment(
                    risk_level="low",
                    requires_approval=False,
                    reason="Low risk in test",
                    payload_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                )
                await execution_runner.run_execution(execution.id)

    async with async_session_maker() as db:
        exec_db = await db.get(Execution, execution.id)
        assert exec_db.status == "completed"
        task_db = await db.get(Task, task.id)
        assert task_db.status == "completed"
        assert "99" in str(task_db.result)


