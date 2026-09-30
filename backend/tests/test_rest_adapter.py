import app.tools.registry
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.adapters.rest import RestApiTool

pytestmark = pytest.mark.asyncio


def make_http_mock(status_code: int, text: str, headers: dict = None):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    mock_resp.headers = headers or {}

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_rest_api_get_success():
    tool = RestApiTool()
    mock_client = make_http_mock(200, '{"result": "ok"}', {"Content-Type": "application/json"})

    # Mock SSRF check to allow, and mock httpx
    with patch.object(tool, "_is_safe_url", return_value=True):
        with patch("httpx.AsyncClient", return_value=mock_client):
            res = await tool.execute(
                "api_request",
                {"url": "https://api.example.com/data", "method": "GET"},
            )
    assert "error" not in res, str(res)
    assert res["status_code"] == 200
    assert res["content"] == '{"result": "ok"}'
    assert res["truncated"] is False


async def test_rest_api_ssrf_localhost_blocked():
    tool = RestApiTool()
    # Don't mock - let real SSRF check run for localhost
    res = await tool.execute("api_request", {"url": "http://localhost:8080/secret"})
    assert "error" in res
    assert "SSRF" in res["error"]


async def test_rest_api_ssrf_metadata_blocked():
    tool = RestApiTool()
    res = await tool.execute("api_request", {"url": "http://169.254.169.254/metadata"})
    assert "error" in res
    assert "SSRF" in res["error"]


async def test_rest_api_missing_url():
    tool = RestApiTool()
    res = await tool.execute("api_request", {})
    assert "error" in res
    assert "url" in res["error"].lower()


async def test_rest_api_invalid_method():
    tool = RestApiTool()
    res = await tool.execute("api_request", {"url": "https://api.example.com", "method": "TRACE"})
    assert "error" in res


async def test_rest_api_content_truncation():
    tool = RestApiTool()
    large_content = "x" * 10000
    mock_client = make_http_mock(200, large_content)

    with patch.object(tool, "_is_safe_url", return_value=True):
        with patch("httpx.AsyncClient", return_value=mock_client):
            res = await tool.execute(
                "api_request",
                {"url": "https://api.example.com/large", "method": "GET"},
            )
    assert res.get("truncated") is True
    assert len(res["content"]) <= 8100


def test_ssrf_check_blocks_private_ips():
    """Unit test the SSRF validator directly."""
    tool = RestApiTool()
    assert tool._is_safe_url("http://localhost/foo") is False
    assert tool._is_safe_url("http://127.0.0.1/foo") is False
    assert tool._is_safe_url("http://169.254.169.254/metadata") is False
    assert tool._is_safe_url("ftp://example.com/data") is False
    assert tool._is_safe_url("not-a-url") is False
