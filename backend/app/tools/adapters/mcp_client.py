"""
mcp_client.py — Official Model Context Protocol (MCP) Client Adapter for Relay.

Provides robust integration with MCP servers over:
1. Streamable HTTP / SSE transport (MCP spec 2024-11-05+)
2. Stdio transport (local subprocess via StdioServerParameters)
3. HTTP fallback transport for legacy servers

Uses official Python MCP SDK (mcp.client).
"""

import asyncio
import json
import logging
import os
import re
import shlex
import sys
import uuid
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse

import httpx

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
try:
    from mcp.client.streamable_http import streamable_http_client
except ImportError:
    streamable_http_client = None

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 8000
MAX_TOOL_NAME_LEN = 128
MAX_PARAM_KEY_LEN = 64
MAX_PARAM_STR_LEN = 4000
MCP_TIMEOUT_SECONDS = 30.0

# Forbidden shell metacharacters in stdio commands to prevent injection
DANGEROUS_CMD_CHARS = re.compile(r"[;&|`$<>]")


class MCPConnectionError(Exception):
    """Raised when connecting to an MCP server fails."""
    pass


class MCPProtocolError(Exception):
    """Raised when an MCP server returns an invalid response."""
    pass


class MCPTimeoutError(Exception):
    """Raised when an MCP operation times out."""
    pass


def parse_mcp_config(credentials: Any) -> Dict[str, Any]:
    """
    Normalizes credentials into a structured MCP configuration dictionary.
    Supports:
      - Plain URL string: "http://localhost:8080/mcp"
      - JSON string or Dict with transport, server_url, command, args, etc.
    """
    if not credentials:
        raise ValueError("Missing MCP credentials or configuration.")

    if isinstance(credentials, str):
        credentials = credentials.strip()
        if credentials.startswith("{") and credentials.endswith("}"):
            try:
                data = json.loads(credentials)
            except Exception:
                data = {"server_url": credentials}
        else:
            data = {"server_url": credentials}
    elif isinstance(credentials, dict):
        data = dict(credentials)
    else:
        data = {"server_url": str(credentials)}

    # Determine transport
    raw_transport = data.get("transport")
    transport = str(raw_transport).lower() if raw_transport else ""
    if not transport or transport == "none":
        if data.get("command"):
            transport = "stdio"
        elif data.get("server_url") or data.get("url") or data.get("access_token"):
            transport = "streamable_http"
        else:
            transport = "streamable_http"

    server_url = (data.get("server_url") or data.get("url") or data.get("access_token") or "").strip()
    command = (data.get("command") or "").strip()
    raw_args = data.get("args") or []
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args) if raw_args.startswith("[") else shlex.split(raw_args)
        except Exception:
            args = shlex.split(raw_args)
    elif isinstance(raw_args, list):
        args = [str(a) for a in raw_args]
    else:
        args = []

    env = data.get("env") or {}
    if not isinstance(env, dict):
        env = {}

    headers = data.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    auth_token = data.get("auth_token") or data.get("token")
    if auth_token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {auth_token}"

    return {
        "transport": transport,
        "server_url": server_url.rstrip("/"),
        "command": command,
        "args": args,
        "env": env,
        "headers": headers,
        "timeout": float(data.get("timeout", MCP_TIMEOUT_SECONDS)),
    }


def validate_mcp_config(config: Dict[str, Any]) -> None:
    """Validates configuration parameters and checks security constraints."""
    transport = config.get("transport")
    if transport in ["streamable_http", "sse", "http"]:
        url = config.get("server_url")
        if not url:
            raise ValueError("Parameter 'server_url' is required for HTTP/SSE MCP transport.")
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted.")
        
        # SSRF Protection: Block cloud metadata service IP (169.254.169.254)
        hostname = (parsed.hostname or "").lower()
        if hostname == "169.254.169.254" or hostname.endswith(".internal"):
            raise ValueError(f"SSRF violation: Host '{hostname}' is forbidden.")

    elif transport == "stdio":
        cmd = config.get("command")
        if not cmd:
            raise ValueError("Parameter 'command' is required for stdio MCP transport.")
        if DANGEROUS_CMD_CHARS.search(cmd):
            raise ValueError(f"Command injection risk: prohibited characters in command '{cmd}'.")
        for arg in config.get("args", []):
            if DANGEROUS_CMD_CHARS.search(arg):
                raise ValueError(f"Command injection risk: prohibited characters in arg '{arg}'.")
    else:
        raise ValueError(f"Unsupported MCP transport '{transport}'. Supported: streamable_http, sse, stdio.")


class MCPClient:
    """
    Production-grade MCP Client managing connections, discovery, and tool execution
    using official MCP SDK protocols and robust fallbacks.
    """

    async def health_check(self, credentials: Any) -> Tuple[bool, Dict[str, Any]]:
        """
        Runs comprehensive health check:
        1. Connects to server
        2. Initializes session
        3. Discovers tools
        Returns (is_healthy, structured_health_dict)
        """
        try:
            config = parse_mcp_config(credentials)
            validate_mcp_config(config)
        except Exception as e:
            return False, {
                "status": "unavailable",
                "message": f"Configuration error: {str(e)}",
                "tool_count": 0,
                "transport": "unknown",
            }

        transport = config["transport"]
        timeout = min(config.get("timeout", 10.0), 15.0)

        try:
            async def _check():
                tools = await self.list_tools(config)
                return tools

            tools = await asyncio.wait_for(_check(), timeout=timeout)
            return True, {
                "status": "healthy",
                "server": config.get("server_url") or config.get("command"),
                "transport": transport,
                "tool_count": len(tools),
                "message": f"Connected to MCP server ({len(tools)} tools discovered).",
            }
        except asyncio.TimeoutError:
            return False, {
                "status": "degraded",
                "transport": transport,
                "tool_count": 0,
                "message": f"MCP server health check timed out after {timeout}s.",
            }
        except Exception as exc:
            return False, {
                "status": "unavailable",
                "transport": transport,
                "tool_count": 0,
                "message": f"MCP connection failed: {str(exc)}",
            }

    async def list_tools(self, credentials: Any) -> List[Dict[str, Any]]:
        """
        Connects, initializes, and retrieves tools list from MCP server.
        Returns list of {"name": str, "description": str, "input_schema": dict}.
        """
        config = parse_mcp_config(credentials)
        validate_mcp_config(config)
        transport = config["transport"]

        if transport == "stdio":
            return await self._list_tools_stdio(config)
        else:
            return await self._list_tools_http(config)

    async def call_tool(
        self,
        credentials: Any,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executes tools/call on the MCP server with validated parameters.
        Returns real output bounded at MAX_CONTENT_CHARS.
        """
        config = parse_mcp_config(credentials)
        validate_mcp_config(config)

        tool_name = str(tool_name).strip()
        if not tool_name or len(tool_name) > MAX_TOOL_NAME_LEN:
            raise ValueError(f"Invalid tool_name length for MCP call.")

        sanitized_args = _sanitize_arguments(arguments or {})

        transport = config["transport"]
        if transport == "stdio":
            return await self._call_tool_stdio(config, tool_name, sanitized_args)
        else:
            return await self._call_tool_http(config, tool_name, sanitized_args)

    # ─────────────────────────────────────────────────────────────────────────
    # Stdio Transport Implementations
    # ─────────────────────────────────────────────────────────────────────────

    async def _list_tools_stdio(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        cmd = config["command"]
        args = config.get("args", [])
        env = dict(os.environ)
        env.update(config.get("env", {}))

        params = StdioServerParameters(command=cmd, args=args, env=env)
        try:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    res = await session.list_tools()
                    tools = []
                    for t in res.tools:
                        input_schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", {})
                        if hasattr(input_schema, "model_dump"):
                            input_schema = input_schema.model_dump()
                        elif not isinstance(input_schema, dict):
                            input_schema = dict(input_schema) if input_schema else {}
                        tools.append({
                            "name": t.name,
                            "description": t.description or "",
                            "input_schema": input_schema,
                        })
                    return tools
        except Exception as e:
            raise MCPConnectionError(f"Failed to list tools via stdio transport: {str(e)}") from e

    async def _call_tool_stdio(
        self, config: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        cmd = config["command"]
        args = config.get("args", [])
        env = dict(os.environ)
        env.update(config.get("env", {}))

        timeout = float(config.get("timeout", MCP_TIMEOUT_SECONDS))

        async def _run():
            params = StdioServerParameters(command=cmd, args=args, env=env)
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    
                    # Process content
                    content_blocks = []
                    raw_text_parts = []
                    for block in result.content:
                        b_type = getattr(block, "type", "text")
                        b_text = getattr(block, "text", "")
                        content_blocks.append({"type": b_type, "text": b_text})
                        if b_text:
                            raw_text_parts.append(b_text)

                    raw_text = "\n".join(raw_text_parts).strip()
                    if len(raw_text) > MAX_CONTENT_CHARS:
                        raw_text = raw_text[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"

                    structured_data = getattr(result, "structured_content", None)
                    is_error = getattr(result, "is_error", False)

                    return {
                        "status": "error" if is_error else "success",
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "content": content_blocks,
                        "raw_text": raw_text,
                        "data": structured_data,
                        "is_error": is_error,
                    }

        try:
            return await asyncio.wait_for(_run(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError) as e:
            raise MCPTimeoutError(f"MCP stdio execution timed out after {timeout}s") from e
        except (FileNotFoundError, OSError, ConnectionRefusedError) as e:
            raise MCPConnectionError(f"Error connecting to MCP stdio server '{cmd}': {str(e)}") from e
        except (MCPTimeoutError, MCPConnectionError):
            raise
        except Exception as e:
            raise MCPProtocolError(f"Error executing MCP stdio tool '{tool_name}': {str(e)}") from e

    # ─────────────────────────────────────────────────────────────────────────
    # HTTP / SSE Transport Implementations
    # ─────────────────────────────────────────────────────────────────────────

    async def _list_tools_http(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        server_url = config["server_url"]
        headers = config.get("headers", {})

        # Try official SDK streamable_http_client if available
        if streamable_http_client:
            try:
                endpoint = f"{server_url}/mcp" if not server_url.endswith("/mcp") else server_url
                async with streamable_http_client(endpoint, headers=headers) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        res = await session.list_tools()
                        tools = []
                        for t in res.tools:
                            schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", {})
                            if hasattr(schema, "model_dump"):
                                schema = schema.model_dump()
                            tools.append({
                                "name": t.name,
                                "description": t.description or "",
                                "input_schema": schema if isinstance(schema, dict) else {},
                            })
                        return tools
            except Exception as e:
                logger.debug(f"streamable_http_client list_tools failed: {e}. Trying fallback.")

        # HTTP JSON-RPC POST /mcp fallback
        req_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/list",
            "params": {}
        }
        all_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": req_id,
            **headers
        }

        async with httpx.AsyncClient(timeout=config.get("timeout", MCP_TIMEOUT_SECONDS)) as client:
            target_url = f"{server_url}/mcp" if not server_url.endswith("/mcp") else server_url
            try:
                resp = await client.post(target_url, json=payload, headers=all_headers)
                if resp.status_code == 200:
                    data = _parse_jsonrpc_response(resp.text)
                    if "result" in data and "tools" in data["result"]:
                        return data["result"]["tools"]
            except Exception:
                pass

            # Legacy SSE fallback: GET /sse or POST /tools/list
            try:
                sse_url = f"{server_url}/sse"
                resp_sse = await client.get(sse_url, timeout=5.0, headers={"Accept": "text/event-stream"})
                if resp_sse.status_code == 200:
                    return [{"name": "mcp_call", "description": "Legacy SSE MCP Server", "input_schema": {}}]
            except Exception:
                pass

        raise MCPConnectionError(f"Could not connect or list tools from MCP server at {server_url}")

    async def _call_tool_http(
        self, config: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        server_url = config["server_url"]
        headers = config.get("headers", {})

        # Try official SDK streamable_http_client if available
        if streamable_http_client:
            try:
                endpoint = f"{server_url}/mcp" if not server_url.endswith("/mcp") else server_url
                async with streamable_http_client(endpoint, headers=headers) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        raw_parts = [getattr(b, "text", "") for b in result.content if getattr(b, "text", "")]
                        raw_text = "\n".join(raw_parts)
                        if len(raw_text) > MAX_CONTENT_CHARS:
                            raw_text = raw_text[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"
                        return {
                            "status": "error" if getattr(result, "is_error", False) else "success",
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "content": [{"type": getattr(b, "type", "text"), "text": getattr(b, "text", "")} for b in result.content],
                            "raw_text": raw_text,
                            "data": getattr(result, "structured_content", None),
                            "is_error": getattr(result, "is_error", False),
                        }
            except Exception as e:
                logger.debug(f"streamable_http_client call_tool failed: {e}. Trying fallback.")

        # HTTP JSON-RPC fallback
        req_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        all_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": req_id,
            **headers
        }

        async with httpx.AsyncClient(timeout=config.get("timeout", MCP_TIMEOUT_SECONDS)) as client:
            target_url = f"{server_url}/mcp" if not server_url.endswith("/mcp") else server_url
            resp = await client.post(target_url, json=payload, headers=all_headers)
            if resp.status_code == 200:
                data = _parse_jsonrpc_response(resp.text)
                if "error" in data:
                    return {
                        "status": "error",
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "content": [],
                        "raw_text": str(data["error"]),
                        "is_error": True,
                    }
                res = data.get("result", {})
                content = res.get("content", [])
                raw_text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict)).strip()
                if len(raw_text) > MAX_CONTENT_CHARS:
                    raw_text = raw_text[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"
                return {
                    "status": "error" if res.get("isError") else "success",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "content": content,
                    "raw_text": raw_text,
                    "is_error": res.get("isError", False),
                }

        raise MCPProtocolError(f"HTTP call to tool '{tool_name}' failed with status {resp.status_code}")


def _sanitize_arguments(args: Dict[str, Any]) -> Dict[str, Any]:
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


def _parse_jsonrpc_response(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("data:") or "\ndata:" in text:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith("data:"):
                json_str = line[5:].strip()
                if json_str:
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        continue
    return json.loads(text)


mcp_client = MCPClient()
