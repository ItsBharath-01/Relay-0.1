import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.adapters.github import GitHubTool
from app.tools.registry.base import ExecutionContext

pytestmark = pytest.mark.asyncio


def make_http_mock(status_code: int, json_data: dict):
    """Creates a properly mocked httpx response."""
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


async def test_github_issue_create_success():
    tool = GitHubTool()
    mock_client = make_http_mock(201, {"html_url": "https://github.com/a/b/issues/1", "number": 1})

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await tool.execute(
            "issue_create",
            {"repository": "owner/repo", "title": "Test Issue", "body": "test"},
            ctx=ExecutionContext(credentials={"access_token": "fake_token"}),
        )
    assert not res.error, str(res.error)
    assert res.status == "success"
    assert res["issue_url"] == "https://github.com/a/b/issues/1"
    assert res["issue_number"] == 1
    # Verify token was passed
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer fake_token"
    assert call_kwargs["json"]["title"] == "Test Issue"


async def test_github_issue_create_missing_params():
    tool = GitHubTool()
    res = await tool.execute(
        "issue_create",
        {"title": "No Repo"},
        ctx=ExecutionContext(credentials="token")
    )
    assert res.status == "error"
    assert "repository" in res.error.lower() or "title" in res.error.lower()


async def test_github_issue_read_success():
    tool = GitHubTool()
    mock_client = make_http_mock(200, {"title": "Test Issue", "state": "open", "body": "test body"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await tool.execute(
            "issue_read",
            {"repository": "owner/repo", "issue_number": 1},
            ctx=ExecutionContext(credentials={"access_token": "fake_token"}),
        )
    assert not res.error, str(res.error)
    assert res.status == "success"
    assert res["title"] == "Test Issue"
    assert res["state"] == "open"


async def test_github_missing_credentials():
    tool = GitHubTool()
    res = await tool.execute(
        "issue_create",
        {"repository": "a/b", "title": "x"},
        ctx=ExecutionContext(credentials=None)
    )
    assert res.status == "error"


async def test_github_api_error():
    tool = GitHubTool()
    mock_client = make_http_mock(422, {"message": "Validation Failed"})
    mock_client.post.return_value.text = "Validation Failed"

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await tool.execute(
            "issue_create",
            {"repository": "owner/repo", "title": "Bad Issue"},
            ctx=ExecutionContext(credentials="fake_token"),
        )
    assert res.status == "error"
    assert "422" in res.error
