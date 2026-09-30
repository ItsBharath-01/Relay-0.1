import app.tools.registry
import pytest
import uuid
import json
from httpx import Response
from unittest.mock import AsyncMock, patch

from app.tools.adapters.mcp_adapter import (
    MCPToolAdapter,
    MCPTransportError,
    _parse_mcp_response,
    _sanitize_arguments
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------
# Utility / Sanitize tests
# ---------------------------------------------------------
def test_parse_mcp_response():
    # Plain JSON
    assert _parse_mcp_response('{"result": "ok"}') == {"result": "ok"}
    # SSE stream format
    sse_text = "data: {\"progress\": 50}\n\ndata: {\"result\": \"ok\"}\n"
    assert _parse_mcp_response(sse_text) == {"result": "ok"}

def test_sanitize_arguments():
    raw = {
        "valid_str": "hello",
        "too_long_str": "a" * 5000,
        "valid_int": 42,
        "valid_list": [1, 2, 3],
        "complex_dict": {"a": "b"}
    }
    safe = _sanitize_arguments(raw)
    assert safe["valid_str"] == "hello"
    assert len(safe["too_long_str"]) == 4000
    assert safe["valid_int"] == 42
    assert safe["valid_list"] == "[1, 2, 3]"
    assert safe["complex_dict"] == '{"a": "b"}'

# ---------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------

async def test_health_check_success():
    adapter = MCPToolAdapter()
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(200, json={"result": {"serverInfo": {"name": "TestServer"}}}, request=AsyncMock())
        
        healthy, msg = await adapter.health_check("http://localhost:8000")
        assert healthy is True
        assert "TestServer" in msg

async def test_health_check_fallback_sse():
    adapter = MCPToolAdapter()
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(404, text="Not Found", request=AsyncMock())
        
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Response(200, text="", request=AsyncMock())
            
            healthy, msg = await adapter.health_check("http://localhost:8000")
            assert healthy is True
            assert "legacy SSE transport" in msg

async def test_execute_streamable_success():
    adapter = MCPToolAdapter()
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200,
            request=AsyncMock(),
            json={
                "result": {
                    "content": [{"type": "text", "text": "Tool output text"}]
                }
            }
        )
        
        res = await adapter.execute(
            action="mcp_call",
            params={"tool_name": "my_tool", "arguments": {"foo": "bar"}},
            credentials="http://localhost:8000"
        )
        
        assert res["tool_name"] == "my_tool"
        assert res["arguments"] == {"foo": "bar"}
        assert res["raw_text"] == "Tool output text"
        assert res["is_error"] is False

async def test_execute_streamable_error_response():
    adapter = MCPToolAdapter()
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(200, json={"error": {"code": -32603, "message": "Internal error"}}, request=AsyncMock())
        
        with pytest.raises(RuntimeError, match="Internal error"):
            await adapter.execute(
                action="mcp_call",
                params={"tool_name": "my_tool"},
                credentials="http://localhost:8000"
            )

async def test_execute_fallback_legacy_sse():
    adapter = MCPToolAdapter()
    
    class MockStream:
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        async def aiter_lines(self):
            yield "data: {\"sessionId\": \"session_123\"}"
            yield "data: {\"result\": {\"content\": [{\"type\": \"text\", \"text\": \"Legacy output\"}]}, \"id\": \"test_req_id\"}"

    with patch("app.tools.adapters.mcp_adapter.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value = "test_req_id"
        
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            # First POST returns 404 to trigger fallback
            # Second POST is the /message endpoint
            mock_post.side_effect = [
                Response(404, text="Not Found", request=AsyncMock()),
                Response(200, text="OK", request=AsyncMock())
            ]
            
            with patch("httpx.AsyncClient.stream") as mock_stream:
                mock_stream.return_value = MockStream()
                
                res = await adapter.execute(
                    action="mcp_call",
                    params={"tool_name": "legacy_tool"},
                    credentials={"access_token": "http://localhost:8000"}
                )
                
                assert res["tool_name"] == "legacy_tool"
                assert res["raw_text"] == "Legacy output"

async def test_verify():
    adapter = MCPToolAdapter()
    
    passed, ev = await adapter.verify(
        action="mcp_call",
        params={"tool_name": "test"},
        result={"tool_name": "test", "raw_text": "Good output", "is_error": False}
    )
    assert passed is True
    assert ev["output_chars"] == 11
    
    passed, ev = await adapter.verify(
        action="mcp_call",
        params={"tool_name": "test"},
        result={"tool_name": "test", "raw_text": "Error!", "is_error": True}
    )
    assert passed is False

