"""
mcp_adapter.py — Real MCP (Model Context Protocol) Tool Adapter for Relay P2-2.

Architecture:
  - Connects to user-registered MCP servers over HTTP+SSE transport (MCP spec §4).
  - Supports both streamable-HTTP (POST with SSE response) and legacy SSE endpoints.
  - Each user can register N MCP servers; each is stored as a Connection with
    app_id="mcp_<server_id>", auth_type="url", encrypted_credentials=<endpoint_url>.
  - execute() calls tools/call on the server and returns the real result.
  - verify() checks that the result content is non-empty and well-formed.
  - Risk classification uses the mcp_call default_risk ("medium") from the capability
    registry; individual tool risk can be escalated by checking tool annotations.

Security:
  - Server URL is stored encrypted at rest via Fernet.
  - Tool names and arguments are validated before transmission.
  - MCP server responses are treated as UNTRUSTED external content.
  - Tool output is bounded at MAX_CONTENT_CHARS to prevent context flooding.
  - No credentials are passed to the LLM at any point.

MCP Transport: HTTP+SSE (Streamable HTTP, MCP spec 2024-11-05 and later).
  POST {server_url}/mcp  → initialize session
  POST {server_url}/mcp  → tools/list
  POST {server_url}/mcp  → tools/call

Fallback: Legacy SSE endpoint (GET /sse + POST /message) for older servers.
"""

import json
import uuid
import logging
from typing import Dict, Any, Optional, Tuple, List

import httpx

from app.tools.registry.base import BaseTool

logger = logging.getLogger(__name__)

# Hard limits to prevent abuse and context flooding
MAX_CONTENT_CHARS = 8000
MAX_TOOL_NAME_LEN = 128
MAX_PARAM_KEY_LEN = 64
MAX_PARAM_STR_LEN = 4000
MCP_TIMEOUT_SECONDS = 30.0

# JSON-RPC version used by MCP
JSONRPC = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPToolAdapter(BaseTool):
    """
    Real MCP tool adapter.

    One instance is registered per MCP connection entry in the database.
    The `credentials` passed to execute() / health_check() is the plaintext
    server URL (already decrypted by ConnectionResolver before arriving here).
    """

    id = "mcp_tool"
    name = "MCP Server Tool"
    tool_type = "mcp"
    provides = ["mcp_call"]
    requires_connection = "mcp"
    required_permissions = ["call_tools"]

    # ─────────────────────────────────────────────────────────────────────────
    # health_check
    # ─────────────────────────────────────────────────────────────────────────

    async def health_check(
        self, credentials: Optional[Any] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies that the MCP server is reachable and responds to initialize.

        credentials: plaintext MCP server base URL (e.g. http://localhost:8080)
        """
        if not credentials:
            return False, "MCP server URL is not configured."

        if isinstance(credentials, dict):
            server_url = credentials.get("access_token", "")
        else:
            server_url = str(credentials)
            
        server_url = server_url.rstrip("/")
        if not server_url:
            return False, "MCP server URL is empty."
            
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                req_id = str(uuid.uuid4())
                payload = _jsonrpc_request(
                    "initialize",
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "relay", "version": "0.2"},
                    },
                    req_id,
                )
                resp = await client.post(
                    f"{server_url}/mcp",
                    json=payload,
                    headers=_mcp_headers(req_id),
                )
                if resp.status_code == 200:
                    body = _parse_mcp_response(resp.text)
                    if "result" in body:
                        sv = body["result"].get("serverInfo", {})
                        name = sv.get("name", "MCP Server")
                        return True, f"Connected to '{name}'"
                    return False, f"Unexpected MCP response: {resp.text[:200]}"
                # Some servers use legacy SSE transport — try GET /sse ping
                resp2 = await client.get(
                    f"{server_url}/sse",
                    timeout=5.0,
                    headers={"Accept": "text/event-stream"},
                )
                if resp2.status_code == 200:
                    return True, "MCP server reachable (legacy SSE transport)"
                return False, f"MCP server returned HTTP {resp.status_code}"
        except httpx.ConnectError:
            return False, f"Cannot connect to MCP server at {server_url}"
        except Exception as exc:
            return False, f"MCP health check error: {exc}"

    # ─────────────────────────────────────────────────────────────────────────
    # execute
    # ─────────────────────────────────────────────────────────────────────────

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        credentials: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool call.

        params:
            tool_name (str):   Name of the MCP tool to call. Required.
            arguments (dict):  Tool arguments dict. Optional; defaults to {}.
            server_url (str):  Override URL (used if credentials is None).

        Returns dict with:
            tool_name, arguments, content (list of content blocks), raw_text
        """
        if not credentials:
            raise ValueError("MCP server URL is not configured for this connection.")
            
        if isinstance(credentials, dict):
            server_url = credentials.get("access_token", "")
        else:
            server_url = str(credentials)
            
        server_url = server_url.rstrip("/")
        if not server_url:
            raise ValueError("MCP server URL is empty.")

        tool_name = str(params.get("tool_name", "")).strip()
        if not tool_name:
            raise ValueError("Parameter 'tool_name' is required for mcp_call.")
        if len(tool_name) > MAX_TOOL_NAME_LEN:
            raise ValueError(f"tool_name exceeds maximum length ({MAX_TOOL_NAME_LEN}).")

        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("Parameter 'arguments' must be a JSON object.")

        # Sanitize argument keys and values
        arguments = _sanitize_arguments(arguments)

        # Try streamable-HTTP transport first, fall back to legacy SSE
        try:
            result = await _call_tool_streamable_http(server_url, tool_name, arguments)
        except MCPTransportError:
            logger.warning(
                "Streamable HTTP transport failed for %s, trying legacy SSE.", server_url
            )
            result = await _call_tool_legacy_sse(server_url, tool_name, arguments)

        # Bound output length
        raw_text = _extract_text_content(result.get("content", []))
        if len(raw_text) > MAX_CONTENT_CHARS:
            raw_text = raw_text[:MAX_CONTENT_CHARS] + "\n…[truncated]"

        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "content": result.get("content", []),
            "raw_text": raw_text,
            "is_error": result.get("isError", False),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # verify
    # ─────────────────────────────────────────────────────────────────────────

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify MCP tool output is non-empty and not an error response.
        """
        tool_name = result.get("tool_name", params.get("tool_name", "unknown"))
        raw_text = result.get("raw_text", "")
        is_error = result.get("is_error", False)

        passed = bool(raw_text) and not is_error
        evidence = {
            "tool_name": tool_name,
            "output_chars": len(raw_text),
            "is_error": is_error,
            "output_preview": raw_text[:200] if raw_text else "",
        }
        return passed, evidence

    # ─────────────────────────────────────────────────────────────────────────
    # list_tools — not part of BaseTool but used by the /connections endpoint
    # ─────────────────────────────────────────────────────────────────────────

    async def list_tools(self, server_url: str) -> List[Dict[str, Any]]:
        """
        Lists all tools available on the MCP server.
        Returns list of {name, description, inputSchema} dicts.
        """
        server_url = server_url.rstrip("/")
        req_id = str(uuid.uuid4())
        payload = _jsonrpc_request("tools/list", {}, req_id)

        async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{server_url}/mcp",
                json=payload,
                headers=_mcp_headers(req_id),
            )
            resp.raise_for_status()
            body = _parse_mcp_response(resp.text)
            if "error" in body:
                raise RuntimeError(f"MCP tools/list error: {body['error']}")
            return body.get("result", {}).get("tools", [])


# ─────────────────────────────────────────────────────────────────────────────
# Internal transport helpers
# ─────────────────────────────────────────────────────────────────────────────

class MCPTransportError(Exception):
    """Raised when the primary transport fails and fallback should be tried."""


def _jsonrpc_request(method: str, params: Dict[str, Any], req_id: str) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": req_id, "method": method, "params": params}


def _mcp_headers(session_id: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Session-Id": session_id,
    }


def _parse_mcp_response(text: str) -> Dict[str, Any]:
    """
    Parse either a plain JSON response or the last data: line of an SSE stream.
    """
    text = text.strip()
    # SSE stream — grab the last data: line
    if text.startswith("data:") or "\ndata:" in text:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith("data:"):
                json_str = line[5:].strip()
                if json_str:
                    return json.loads(json_str)
    # Plain JSON
    return json.loads(text)


async def _call_tool_streamable_http(
    server_url: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """Call a tool using the streamable-HTTP (POST /mcp) transport."""
    req_id = str(uuid.uuid4())
    payload = _jsonrpc_request(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        req_id,
    )
    try:
        async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{server_url}/mcp",
                json=payload,
                headers=_mcp_headers(req_id),
            )
            if resp.status_code == 404:
                raise MCPTransportError("POST /mcp returned 404 — trying legacy SSE")
            resp.raise_for_status()
            body = _parse_mcp_response(resp.text)
            if "error" in body:
                raise RuntimeError(f"MCP tools/call error: {body['error']}")
            return body.get("result", {})
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise MCPTransportError(f"Streamable HTTP transport failed: {exc}") from exc


async def _call_tool_legacy_sse(
    server_url: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Call a tool using the legacy SSE transport:
      GET /sse         → get sessionId from endpoint event
      POST /message    → send tools/call request
      GET /sse stream  → wait for result event
    """
    req_id = str(uuid.uuid4())
    session_id: Optional[str] = None

    # Step 1: Establish SSE session to get sessionId
    async with httpx.AsyncClient(timeout=15.0) as client:
        async with client.stream("GET", f"{server_url}/sse") as stream:
            async for line in stream.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        data = json.loads(data_str)
                        session_id = data.get("sessionId") or data.get("session_id")
                        if session_id:
                            break
                    except json.JSONDecodeError:
                        # Some servers send the endpoint URL as plain text
                        if "/message" in data_str:
                            session_id = data_str.split("sessionId=")[-1].split("&")[0] if "sessionId=" in data_str else req_id
                            break

    if not session_id:
        raise RuntimeError("Could not obtain MCP session ID from SSE endpoint.")

    # Step 2: Send tools/call via POST /message
    payload = _jsonrpc_request(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        req_id,
    )
    async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
        msg_resp = await client.post(
            f"{server_url}/message?sessionId={session_id}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        msg_resp.raise_for_status()

        # Step 3: Read SSE stream for the result
        async with client.stream(
            "GET",
            f"{server_url}/sse?sessionId={session_id}",
            headers={"Accept": "text/event-stream"},
        ) as stream:
            async for line in stream.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        body = json.loads(data_str)
                        if body.get("id") == req_id:
                            if "error" in body:
                                raise RuntimeError(f"MCP tools/call error: {body['error']}")
                            return body.get("result", {})
                    except json.JSONDecodeError:
                        continue

    raise RuntimeError("MCP tools/call: no result received from legacy SSE stream.")


def _extract_text_content(content: List[Any]) -> str:
    """Extract plain text from MCP content blocks."""
    parts = []
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "resource":
                resource = block.get("resource", {})
                if "text" in resource:
                    parts.append(resource["text"])
                elif "uri" in resource:
                    parts.append(f"[Resource: {resource['uri']}]")
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(p for p in parts if p).strip()


def _sanitize_arguments(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize MCP tool arguments:
    - Keys must be strings and within length limit.
    - String values are capped at MAX_PARAM_STR_LEN.
    - Nested dicts/lists are JSON-encoded and capped.
    """
    safe: Dict[str, Any] = {}
    for k, v in args.items():
        if not isinstance(k, str) or len(k) > MAX_PARAM_KEY_LEN:
            continue
        if isinstance(v, str):
            safe[k] = v[:MAX_PARAM_STR_LEN]
        elif isinstance(v, (int, float, bool)) or v is None:
            safe[k] = v
        else:
            # Serialize complex values to string and cap
            try:
                safe[k] = json.dumps(v)[:MAX_PARAM_STR_LEN]
            except Exception:
                safe[k] = str(v)[:MAX_PARAM_STR_LEN]
    return safe
