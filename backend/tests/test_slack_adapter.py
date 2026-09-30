import app.tools.registry
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.adapters.slack import SlackTool

pytestmark = pytest.mark.asyncio


def make_http_mock(status_code: int, json_data: dict):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = str(json_data)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_slack_message_send_success():
    tool = SlackTool()
    mock_client = make_http_mock(200, {"ok": True, "channel": "C12345", "ts": "123.45"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await tool.execute(
            "message_send",
            {"channel": "general", "text": "Hello world!"},
            credentials={"access_token": "xoxb-fake"},
        )
    assert "error" not in res, str(res)
    assert res["status"] == "success"
    assert res["channel"] == "C12345"
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer xoxb-fake"
    assert call_kwargs["json"]["text"] == "Hello world!"


async def test_slack_missing_credentials():
    tool = SlackTool()
    res = await tool.execute("message_send", {"channel": "general", "text": "hi"}, credentials=None)
    assert "error" in res


async def test_slack_missing_params():
    tool = SlackTool()
    res = await tool.execute("message_send", {"text": "no channel"}, credentials="xoxb-fake")
    assert "error" in res
    assert "channel" in res["error"].lower()


async def test_slack_api_error():
    tool = SlackTool()
    mock_client = make_http_mock(200, {"ok": False, "error": "channel_not_found"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await tool.execute(
            "message_send",
            {"channel": "nonexistent", "text": "hi"},
            credentials="xoxb-fake",
        )
    assert "error" in res
    assert "channel_not_found" in res["error"]
