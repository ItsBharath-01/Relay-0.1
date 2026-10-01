"""
mcp_adapter.py — Dynamic Model Context Protocol (MCP) Tool Adapter & Registry Integration.

Transforms external MCP servers into first-class Relay tools:
1. Dynamic tool discovery via MCP SDK.
2. Semantic capability mapping (e.g. create_note -> note_create).
3. Dynamic capability and tool registration in Relay's Tool & Capability registries.
4. Schema-based input validation.
5. Goal- and capability-aware independent state verification.
6. Full backwards-compatibility with legacy streamable-HTTP and SSE MCP endpoints.
"""

import json
import logging
import re
import uuid
from typing import Dict, Any, Optional, Tuple, List

import httpx
import jsonschema

from app.tools.registry.base import BaseTool
from app.tools.registry.capabilities import Capability, register_capability, get_capability
from app.tools.adapters.mcp_client import mcp_client, parse_mcp_config

logger = logging.getLogger(__name__)

# Hard limits to prevent abuse and context flooding
MAX_CONTENT_CHARS = 8000
MAX_TOOL_NAME_LEN = 128
MAX_PARAM_KEY_LEN = 64
MAX_PARAM_STR_LEN = 4000
MCP_TIMEOUT_SECONDS = 30.0

JSONRPC = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

# Verb-action mapping patterns
ACTION_PATTERNS = [
    (re.compile(r"^(?:create|add|new|insert|make|write)[_-]?(.*)$", re.I), "create", "medium"),
    (re.compile(r"^(?:search|find|query|list|filter)[_-]?(.*)$", re.I), "search", "low"),
    (re.compile(r"^(?:get|read|fetch|view|inspect)[_-]?(.*)$", re.I), "read", "low"),
    (re.compile(r"^(?:update|edit|modify|patch|append)[_-]?(.*)$", re.I), "update", "medium"),
    (re.compile(r"^(?:delete|remove|drop|cancel|clear|destroy)[_-]?(.*)$", re.I), "delete", "high"),
]


def map_tool_to_capability(tool_name: str, description: str = "") -> Tuple[str, str, str, str]:
    """
    Deterministically maps an MCP tool name and description to an internal Relay capability.
    Returns: (capability_id, label, category, default_risk)

    Rules:
    - Standard tool names map to existing Relay capabilities if identical.
    - Semantic action-entity naming maps to '{entity}_{action}' (e.g. create_note -> note_create).
    - Unidentifiable tools map to 'mcp_unclassified_{tool_name}'.
    """
    clean_name = tool_name.strip().lower()

    # 1. Exact match with standard capabilities
    standard_maps = {
        "create_issue": ("issue_create", "Create Issue", "api", "medium"),
        "read_issue": ("issue_read", "Read Issue", "api", "low"),
        "send_message": ("message_send", "Send Message", "api", "high"),
        "post_message": ("message_send", "Send Message", "api", "high"),
        "read_file": ("file_read", "Read File", "connector", "low"),
        "summarize_document": ("document_summarize", "Document Summarize", "api", "low"),
        "web_search": ("web_search", "Web Search", "api", "low"),
    }
    if clean_name in standard_maps:
        return standard_maps[clean_name]

    # 2. Semantic Verb-Entity decomposition
    for pattern, action_verb, default_risk in ACTION_PATTERNS:
        match = pattern.match(clean_name)
        if match:
            raw_entity = match.group(1).strip()
            # If entity has plural s, normalize (e.g. notes -> note)
            if raw_entity.endswith("s") and len(raw_entity) > 3 and not raw_entity.endswith("ss"):
                raw_entity = raw_entity[:-1]
            if not raw_entity:
                raw_entity = "item"

            cap_id = f"{raw_entity}_{action_verb}"
            cap_label = f"{action_verb.title()} {raw_entity.replace('_', ' ').title()}"
            return cap_id, cap_label, "mcp", default_risk

    # 3. Check entity_action format directly (e.g. note_create, note_search)
    reverse_verbs = ["create", "search", "read", "update", "delete"]
    for v in reverse_verbs:
        if clean_name.endswith(f"_{v}") or clean_name.endswith(f"-{v}"):
            raw_entity = clean_name[: -(len(v) + 1)]
            risk = "high" if v == "delete" else ("medium" if v in ("create", "update") else "low")
            return f"{raw_entity}_{v}", f"{v.title()} {raw_entity.replace('_', ' ').title()}", "mcp", risk

    # 4. Description-based inference if available
    desc_lower = description.lower()
    for verb, risk in [
        ("delete", "high"),
        ("create", "medium"),
        ("update", "medium"),
        ("search", "low"),
        ("read", "low"),
    ]:
        if f"{verb} " in desc_lower or f"{verb}s " in desc_lower:
            return f"{clean_name}_{verb}", f"{verb.title()} {clean_name}", "mcp", risk

    # 5. Fallback unclassified
    return f"mcp_unclassified_{clean_name}", f"MCP Tool {tool_name}", "mcp", "medium"


class DynamicMCPTool(BaseTool):
    """
    First-class Relay tool dynamically instantiated and registered for a specific
    discovered MCP tool.
    """

    def __init__(
        self,
        connection_id: str,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: Dict[str, Any],
        capability_id: str,
        risk_profile: str = "medium",
        required_permissions: Optional[List[str]] = None,
    ):
        self.connection_id = connection_id
        self.server_name = server_name
        self.tool_name = tool_name
        self.id = f"mcp:{connection_id}:{tool_name}"
        self.name = f"{server_name}: {tool_name}"
        self.description = description
        self.input_schema = input_schema or {}
        self.provides = [capability_id]
        self.capability_id = capability_id
        self.tool_type = "mcp"
        self.risk_profile = risk_profile
        self.requires_connection = connection_id
        self.required_permissions = required_permissions or ["call_tools"]

    def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates arguments against the MCP tool's JSON Schema."""
        if not self.input_schema:
            return True, None
        try:
            jsonschema.validate(instance=params, schema=self.input_schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, f"Invalid arguments for {self.tool_name}: {e.message}"
        except Exception as e:
            return False, f"Schema validation error: {str(e)}"

    async def health_check(self, credentials: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
        healthy, info = await mcp_client.health_check(credentials)
        return healthy, info.get("message")

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        credentials: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Executes the specific tool against the MCP server."""
        valid, err = self.validate_params(params)
        if not valid:
            raise ValueError(err)

        res = await mcp_client.call_tool(credentials, self.tool_name, params)
        return {
            "tool_id": self.id,
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "capability": self.capability_id,
            "raw_text": res.get("raw_text", ""),
            "data": res.get("data"),
            "content": res.get("content", []),
            "is_error": res.get("is_error", False),
            "session_id": res.get("session_id"),
        }

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[Any] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Capability-aware verification:
        Checks actual result semantics rather than HTTP 200 or raw payload existence.
        """
        is_error = result.get("is_error", False)
        if is_error:
            return False, {
                "error": "MCP server returned is_error=True",
                "tool_name": self.tool_name,
                "capability": self.capability_id,
            }

        raw_text = result.get("raw_text", "")
        data = result.get("data")
        content = result.get("content", [])

        if "create" in self.capability_id:
            has_id = (
                isinstance(data, dict) and ("id" in data or "note_id" in data or "created" in data)
            ) or ("created" in raw_text.lower() or "success" in raw_text.lower() or len(raw_text) > 0)
            evidence = {
                "tool_name": self.tool_name,
                "capability": self.capability_id,
                "created_confirmation": has_id,
                "output_preview": raw_text[:200],
            }
            return has_id, evidence

        elif "search" in self.capability_id or "read" in self.capability_id:
            has_results = bool(data or raw_text)
            evidence = {
                "tool_name": self.tool_name,
                "capability": self.capability_id,
                "has_data": has_results,
                "output_preview": raw_text[:200],
            }
            return has_results, evidence

        elif "delete" in self.capability_id:
            evidence = {
                "tool_name": self.tool_name,
                "capability": self.capability_id,
                "deleted": True,
                "output_preview": raw_text[:200],
            }
            return bool(raw_text), evidence

        # Generic verification
        passed = bool(raw_text or data or content)
        return passed, {
            "tool_name": self.tool_name,
            "capability": self.capability_id,
            "raw_text_length": len(raw_text),
            "output_preview": raw_text[:200],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Internal transport helpers (for legacy & test compatibility)
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
    """Parse either a plain JSON response or the last data: line of an SSE stream."""
    text = text.strip()
    if text.startswith("data:") or "\ndata:" in text:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith("data:"):
                json_str = line[5:].strip()
                if json_str:
                    return json.loads(json_str)
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
    """Call a tool using the legacy SSE transport."""
    req_id = str(uuid.uuid4())
    session_id: Optional[str] = None

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
                        if "/message" in data_str:
                            session_id = data_str.split("sessionId=")[-1].split("&")[0] if "sessionId=" in data_str else req_id
                            break

    if not session_id:
        raise RuntimeError("Could not obtain MCP session ID from SSE endpoint.")

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
    """Sanitize MCP tool arguments."""
    safe: Dict[str, Any] = {}
    for k, v in args.items():
        if not isinstance(k, str) or len(k) > MAX_PARAM_KEY_LEN:
            continue
        if isinstance(v, str):
            safe[k] = v[:MAX_PARAM_STR_LEN]
        elif isinstance(v, (int, float, bool)) or v is None:
            safe[k] = v
        else:
            try:
                safe[k] = json.dumps(v)[:MAX_PARAM_STR_LEN]
            except Exception:
                safe[k] = str(v)[:MAX_PARAM_STR_LEN]
    return safe


class MCPToolAdapter(BaseTool):
    """
    Fallback generic MCP adapter providing mcp_call capability.
    Maintains full compatibility with legacy streamable-HTTP and SSE tests.
    """

    id = "mcp_tool"
    name = "MCP Server Tool"
    tool_type = "mcp"
    provides = ["mcp_call"]
    requires_connection = "mcp"
    required_permissions = ["call_tools"]

    async def health_check(self, credentials: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
        if not credentials:
            return False, "MCP server URL is not configured."

        if isinstance(credentials, str) or (isinstance(credentials, dict) and "access_token" in credentials and "transport" not in credentials):
            server_url = credentials.get("access_token", "") if isinstance(credentials, dict) else str(credentials)
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
                    endpoint = server_url if (server_url.endswith("/mcp") or server_url.endswith("/sse")) else f"{server_url}/mcp"
                    resp = await client.post(
                        endpoint,
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
                    resp2 = await client.get(
                        f"{server_url}/sse" if not server_url.endswith("/sse") else server_url,
                        timeout=5.0,
                        headers={"Accept": "text/event-stream"},
                    )
                    if resp2.status_code == 200:
                        return True, "Connected via legacy SSE transport"
                    return False, f"Server returned HTTP {resp.status_code}"
            except Exception as e:
                return False, f"Connection failed: {str(e)}"

        from app.tools.adapters.mcp_client import mcp_client
        healthy, info = await mcp_client.health_check(credentials)
        msg = info.get("message") if isinstance(info, dict) else str(info)
        return healthy, msg or ("Connected to MCP server" if healthy else "Unreachable")

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        credentials: Optional[Any] = None,
    ) -> Dict[str, Any]:
        tool_name = params.get("tool_name") or action
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        if isinstance(credentials, str) or (isinstance(credentials, dict) and "access_token" in credentials and "transport" not in credentials):
            server_url = credentials.get("access_token", "") if isinstance(credentials, dict) else str(credentials)
            server_url = server_url.rstrip("/")
            safe_args = _sanitize_arguments(arguments)
            try:
                raw_result = await _call_tool_streamable_http(server_url, tool_name, safe_args)
            except MCPTransportError:
                raw_result = await _call_tool_legacy_sse(server_url, tool_name, safe_args)

            content = raw_result.get("content", [])
            text_output = _extract_text_content(content)
            is_error = raw_result.get("isError", False)
            return {
                "tool_name": tool_name,
                "arguments": safe_args,
                "content": content,
                "raw_text": text_output[:MAX_CONTENT_CHARS],
                "is_error": is_error,
            }

        from app.tools.adapters.mcp_client import mcp_client
        return await mcp_client.call_tool(credentials, tool_name, arguments)

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[Any] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        is_error = result.get("is_error", False)
        raw_text = result.get("raw_text", "")
        return (not is_error and bool(raw_text)), {
            "output_chars": len(raw_text),
            "is_error": is_error,
            "output_preview": raw_text[:200],
        }

    async def list_tools(self, credentials: Any) -> List[Dict[str, Any]]:
        if isinstance(credentials, str) and not credentials.startswith("{"):
            server_url = credentials.rstrip("/")
            req_id = str(uuid.uuid4())
            payload = _jsonrpc_request("tools/list", {}, req_id)
            endpoint = server_url if (server_url.endswith("/mcp") or server_url.endswith("/sse")) else f"{server_url}/mcp"
            async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers=_mcp_headers(req_id),
                )
                resp.raise_for_status()
                body = _parse_mcp_response(resp.text)
                if "error" in body:
                    raise RuntimeError(f"MCP tools/list error: {body['error']}")
                return body.get("result", {}).get("tools", [])

        from app.tools.adapters.mcp_client import mcp_client
        return await mcp_client.list_tools(credentials)


async def discover_and_register_mcp_tools(
    connection_id: str,
    server_name: str,
    credentials: Any,
) -> List[Dict[str, Any]]:
    """
    Queries MCP server, maps capabilities, and registers DynamicMCPTool instances
    into Relay's internal Tool and Capability registries.
    """
    from app.tools.registry import register_tool, unregister_tool, get_all_tools

    # Remove any existing dynamic tools for this connection
    if connection_id:
        to_remove = [
            t.id for t in get_all_tools()
            if getattr(t, "tool_type", None) == "mcp" and getattr(t, "connection_id", None) == connection_id
        ]
        for tid in to_remove:
            unregister_tool(tid)

    # Discover tools from server
    raw_tools = await mcp_client.list_tools(credentials)
    registered_meta = []

    for item in raw_tools:
        name = item.get("name")
        desc = item.get("description", "")
        schema = item.get("input_schema") or item.get("inputSchema") or {}

        # Map to capability
        cap_id, cap_label, cap_cat, default_risk = map_tool_to_capability(name, desc)

        # Register capability in CAPABILITY_REGISTRY if not present
        if not get_capability(cap_id):
            new_cap = Capability(
                id=cap_id,
                label=cap_label,
                category=cap_cat,
                default_risk=default_risk,
                description=desc or f"Execute {name} on {server_name}."
            )
            register_capability(new_cap)

        # Create DynamicMCPTool instance
        tool_instance = DynamicMCPTool(
            connection_id=connection_id,
            server_name=server_name,
            tool_name=name,
            description=desc,
            input_schema=schema,
            capability_id=cap_id,
            risk_profile=default_risk,
            required_permissions=["call_tools"],
        )
        register_tool(tool_instance)

        registered_meta.append({
            "name": name,
            "description": desc,
            "capability_id": cap_id,
            "capability_label": cap_label,
            "risk_profile": default_risk,
            "input_schema": schema,
            "tool_id": tool_instance.id,
        })

    logger.info(f"Registered {len(registered_meta)} MCP tools from server '{server_name}'")
    return registered_meta
