"""
mcp_client.py — Official Model Context Protocol (MCP) Client Adapter for Relay.

Provides robust integration with MCP servers over:
1. Streamable HTTP transport (MCP spec 2024-11-05+)
2. SSE transport
3. Stdio transport (local subprocess via StdioServerParameters)

Maintains active session persistence using the official MCP Python SDK:
- Establishes sessions via official StreamableHTTPTransport and ClientSession
- Captures the server-provided session ID
- Preserves the session across list_tools(), tool calls, and health checks
- Recovers and reconnects when sessions expire
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import shlex
import sys
import time
import uuid
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse

import httpx

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
try:
    from mcp.client.streamable_http import StreamableHTTPTransport, streamable_http_client
    from mcp.shared._compat import resync_tracer
    from mcp.shared._context_streams import create_context_streams
    from mcp.shared._httpx_utils import create_mcp_http_client
except ImportError:
    StreamableHTTPTransport = None
    streamable_http_client = None

from app.core.config import settings

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
        "is_trusted_operator": bool(data.get("is_trusted_operator", False)),
        "user_id": data.get("user_id"),
        "connection_id": data.get("connection_id"),
    }


def validate_mcp_config(config: Dict[str, Any]) -> None:
    """Validates configuration parameters and checks security constraints."""
    transport = config.get("transport")
    if transport in ["streamable_http", "sse", "http"]:
        url = config.get("server_url")
        if not url:
            raise ValueError("Parameter 'server_url' is required for HTTP/SSE MCP transport.")
        from app.security.ssrf import validate_and_resolve_url, SSRFError
        try:
            validate_and_resolve_url(url)
        except SSRFError as se:
            raise ValueError(f"SSRF violation: {se}")

    elif transport == "stdio":
        cmd = config.get("command")
        if not cmd:
            raise ValueError("Parameter 'command' is required for stdio MCP transport.")
        if DANGEROUS_CMD_CHARS.search(cmd):
            raise ValueError(f"Command injection risk: prohibited characters in command '{cmd}'.")
        for arg in config.get("args", []):
            if DANGEROUS_CMD_CHARS.search(arg):
                raise ValueError(f"Command injection risk: prohibited characters in arg '{arg}'.")

        # P0-2: Stdio is strictly forbidden from end-user self-registration
        # Only operator-configured trusted servers are permitted.
        if not config.get("is_trusted_operator", False):
            raise ValueError(
                "Stdio transport is restricted to operator-configured servers (RELAY_TRUSTED_MCP_SERVERS). "
                "End users cannot register arbitrary stdio commands."
            )
    else:
        raise ValueError(f"Unsupported MCP transport '{transport}'. Supported: streamable_http, sse, stdio.")


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


def _get_session_key(config: Dict[str, Any]) -> str:
    """
    P0-2: Isolates session keys per tenant/user and connection.
    Key structure: (user_id, connection_id, transport_target)
    """
    user_id = str(config.get("user_id") or "global")
    connection_id = str(config.get("connection_id") or "default")
    transport = config.get("transport", "")

    if transport == "stdio":
        cmd = config.get("command", "")
        args = " ".join(config.get("args", []))
        target = f"stdio:{cmd}:{args}"
    else:
        url = config.get("server_url", "")
        target = f"{transport}:{url.rstrip('/')}"

    return f"{user_id}:{connection_id}:{target}"


# ─────────────────────────────────────────────────────────────────────────────
# MCPSessionWorker: Active Persistent Session using Official MCP SDK
# ─────────────────────────────────────────────────────────────────────────────

class MCPSessionWorker:
    """
    Dedicated worker running an official MCP ClientSession within its own task.
    Preserves active session state and server session ID across operations.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.transport_type = config.get("transport", "streamable_http")
        self.session_id: Optional[str] = None
        self.server_info: Optional[Any] = None
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ready_event: asyncio.Event = asyncio.Event()
        self._init_error: Optional[Exception] = None
        self._task: Optional[asyncio.Task] = None
        self._stopped: bool = False
        self.last_active: float = time.time()

    def is_alive(self) -> bool:
        try:
            current_loop = asyncio.get_running_loop()
            if self._loop != current_loop:
                return False
        except Exception:
            return False
        return self._task is not None and not self._task.done() and not self._stopped

    async def start(self, timeout: float = 15.0) -> None:
        self._task = asyncio.create_task(self._run_loop())
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._stopped = True
            if self._task and not self._task.done():
                self._task.cancel()
            raise MCPTimeoutError(f"MCP server session handshake timed out after {timeout}s.")

        if self._init_error:
            self._stopped = True
            raise MCPConnectionError(f"Failed to initialize MCP session: {self._init_error}") from self._init_error

    async def _run_loop(self) -> None:
        try:
            if self.transport_type == "stdio":
                await self._run_stdio()
            elif self.transport_type == "sse":
                await self._run_sse()
            else:
                await self._run_streamable_http()
        except (asyncio.CancelledError, GeneratorExit):
            pass
        except Exception as e:
            self._init_error = e
            self._ready_event.set()
            # Drain queue with exception
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    if item and len(item) == 3 and not item[2].done():
                        item[2].set_exception(e)
                except Exception:
                    pass
        finally:
            self._stopped = True

    async def _run_streamable_http(self) -> None:
        if not StreamableHTTPTransport:
            raise MCPConnectionError("mcp.client.streamable_http is not available in MCP SDK.")

        url = self.config["server_url"]
        endpoint = url.rstrip("/")
        if not (endpoint.endswith("/mcp") or endpoint.endswith("/sse")):
            endpoint = f"{endpoint}/mcp"

        transport = StreamableHTTPTransport(endpoint)
        client = create_mcp_http_client()
        headers = self.config.get("headers", {})
        if headers:
            client.headers.update(headers)

        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(client)
            read_stream_writer, read_stream = create_context_streams(0)
            write_stream, write_stream_reader = create_context_streams(0)

            async with (
                read_stream_writer,
                read_stream,
                write_stream,
                write_stream_reader,
                anyio.create_task_group() as tg,
            ):
                def start_get_stream() -> None:
                    tg.start_soon(transport.handle_get_stream, client, read_stream_writer)

                tg.start_soon(
                    transport.post_writer,
                    client,
                    write_stream_reader,
                    read_stream_writer,
                    write_stream,
                    start_get_stream,
                    tg,
                )

                async with ClientSession(read_stream, write_stream) as session:
                    init_res = await session.initialize()
                    self.session_id = transport.session_id
                    self.server_info = getattr(init_res, "server_info", None)
                    logger.info(f"Streamable HTTP session initialized: ID={self.session_id}")
                    self._ready_event.set()

                    await self._process_queue(session)

                if transport.session_id:
                    try:
                        await transport.terminate_session(client)
                    except Exception:
                        pass
                tg.cancel_scope.cancel()
            await resync_tracer()

    async def _run_sse(self) -> None:
        url = self.config["server_url"]
        headers = self.config.get("headers", {})
        async with sse_client(url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                init_res = await session.initialize()
                self.server_info = getattr(init_res, "server_info", None)
                self._ready_event.set()

                await self._process_queue(session)

    async def _run_stdio(self) -> None:
        cmd = self.config["command"]
        args = self.config.get("args", [])
        env = {**os.environ, **self.config.get("env", {})}
        parameters = StdioServerParameters(command=cmd, args=args, env=env)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                init_res = await session.initialize()
                self.server_info = getattr(init_res, "server_info", None)
                self._ready_event.set()

                await self._process_queue(session)

    async def _process_queue(self, session: ClientSession) -> None:
        try:
            while not self._stopped:
                try:
                    item = await self._queue.get()
                except (asyncio.CancelledError, GeneratorExit):
                    break
                if item is None:
                    break
                action, args, fut = item
                self.last_active = time.time()
                try:
                    if action == "list_tools":
                        res = await session.list_tools()
                        if not fut.done():
                            fut.set_result(res)
                    elif action == "call_tool":
                        res = await session.call_tool(args["name"], args["arguments"])
                        if not fut.done():
                            fut.set_result(res)
                    elif action == "ping":
                        await session.send_ping()
                        if not fut.done():
                            fut.set_result(True)
                except Exception as op_err:
                    if not fut.done():
                        fut.set_exception(op_err)
                finally:
                    self._queue.task_done()
        except (asyncio.CancelledError, GeneratorExit):
            pass

    async def list_tools(self) -> Any:
        fut = asyncio.get_running_loop().create_future()
        await self._queue.put(("list_tools", {}, fut))
        return await fut

    async def call_tool(self, name: str, arguments: dict) -> Any:
        fut = asyncio.get_running_loop().create_future()
        await self._queue.put(("call_tool", {"name": name, "arguments": arguments}, fut))
        return await fut

    async def ping(self) -> bool:
        fut = asyncio.get_running_loop().create_future()
        await self._queue.put(("ping", {}, fut))
        return await fut

    async def stop(self) -> None:
        self._stopped = True
        try:
            if self._task and not self._task.done():
                await self._queue.put(None)
                try:
                    await asyncio.wait_for(self._task, timeout=1.5)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    if not self._task.done():
                        self._task.cancel()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# MCPSessionManager: Session Cache & Lifecycle Pool
# ─────────────────────────────────────────────────────────────────────────────

class MCPSessionManager:
    """Pool of active MCP sessions indexed by server endpoint or command."""

    def __init__(self):
        self._sessions: Dict[str, MCPSessionWorker] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get_or_create_session(self, config: Dict[str, Any], timeout: float = 15.0) -> MCPSessionWorker:
        key = _get_session_key(config)
        async with self._lock:
            worker = self._sessions.get(key)
            if worker is not None:
                if worker.is_alive():
                    return worker
                else:
                    self._sessions.pop(key, None)
                    try:
                        await worker.stop()
                    except Exception:
                        pass

            worker = MCPSessionWorker(config)
            await worker.start(timeout=timeout)
            self._sessions[key] = worker
            return worker

    async def evict_session(self, config: Dict[str, Any]) -> None:
        key = _get_session_key(config)
        async with self._lock:
            worker = self._sessions.pop(key, None)
            if worker:
                await worker.stop()

    async def close_session(self, config: Dict[str, Any]) -> None:
        await self.evict_session(config)

    async def close_all(self) -> None:
        async with self._lock:
            for worker in list(self._sessions.values()):
                await worker.stop()
            self._sessions.clear()


# ─────────────────────────────────────────────────────────────────────────────
# MCPClient: Public Facade for Relay
# ─────────────────────────────────────────────────────────────────────────────

class MCPClient:
    """
    Production MCP Client managing connection lifecycle, tool discovery,
    and invocation over persistent official SDK sessions.
    """

    def __init__(self):
        self.session_manager = MCPSessionManager()

    async def health_check(self, credentials: Any) -> Tuple[bool, Dict[str, Any]]:
        """
        Runs comprehensive health check:
        1. Connects or reuses active session
        2. Performs initialize handshake
        3. Lists available tools
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
            worker = await self.session_manager.get_or_create_session(config, timeout=timeout)
            t_res = await asyncio.wait_for(worker.list_tools(), timeout=timeout)
            tool_count = len(t_res.tools) if hasattr(t_res, "tools") else len(t_res)

            return True, {
                "status": "healthy",
                "server": config.get("server_url") or config.get("command"),
                "transport": transport,
                "session_id": worker.session_id,
                "tool_count": tool_count,
                "message": f"Connected to MCP server ({tool_count} tools discovered).",
            }
        except asyncio.TimeoutError:
            await self.session_manager.evict_session(config)
            return False, {
                "status": "degraded",
                "transport": transport,
                "tool_count": 0,
                "message": f"MCP server health check timed out after {timeout}s.",
            }
        except Exception as exc:
            await self.session_manager.evict_session(config)
            return False, {
                "status": "unavailable",
                "transport": transport,
                "tool_count": 0,
                "message": f"MCP connection failed: {str(exc)}",
            }

    async def list_tools(self, credentials: Any) -> List[Dict[str, Any]]:
        """
        Retrieves tools list using active official SDK session.
        Auto-reconnects once if the existing session expired or was terminated.
        """
        config = parse_mcp_config(credentials)
        validate_mcp_config(config)

        timeout = min(config.get("timeout", 15.0), 20.0)

        for attempt in range(2):
            try:
                worker = await self.session_manager.get_or_create_session(config, timeout=timeout)
                res = await asyncio.wait_for(worker.list_tools(), timeout=timeout)
                raw_tools = getattr(res, "tools", res) if res else []
                tools: List[Dict[str, Any]] = []
                for t in raw_tools:
                    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", {})
                    if hasattr(schema, "model_dump"):
                        schema = schema.model_dump()
                    tools.append({
                        "name": getattr(t, "name", str(t)),
                        "description": getattr(t, "description", "") or "",
                        "input_schema": schema if isinstance(schema, dict) else {},
                    })
                return tools
            except Exception as e:
                logger.warning(f"MCP list_tools attempt {attempt + 1} failed: {e}")
                await self.session_manager.evict_session(config)
                if attempt == 1:
                    raise MCPConnectionError(f"Could not list tools from MCP server: {e}") from e

        return []

    async def call_tool(
        self,
        credentials: Any,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executes tools/call on the active MCP session.
        Auto-reconnects once if the existing session expired or was terminated.
        """
        config = parse_mcp_config(credentials)
        validate_mcp_config(config)

        tool_name = str(tool_name).strip()
        if not tool_name or len(tool_name) > MAX_TOOL_NAME_LEN:
            raise ValueError("Invalid tool_name length for MCP call.")

        sanitized_args = _sanitize_arguments(arguments or {})
        timeout = min(config.get("timeout", MCP_TIMEOUT_SECONDS), 45.0)

        for attempt in range(2):
            try:
                worker = await self.session_manager.get_or_create_session(config, timeout=15.0)
                result = await asyncio.wait_for(
                    worker.call_tool(tool_name, sanitized_args),
                    timeout=timeout,
                )

                content_list = getattr(result, "content", []) or []
                raw_parts = [getattr(b, "text", "") for b in content_list if getattr(b, "text", "")]
                raw_text = "\n".join(raw_parts)
                if len(raw_text) > MAX_CONTENT_CHARS:
                    raw_text = raw_text[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"

                is_error = getattr(result, "is_error", False)
                return {
                    "status": "error" if is_error else "success",
                    "tool_name": tool_name,
                    "arguments": sanitized_args,
                    "content": [
                        {"type": getattr(b, "type", "text"), "text": getattr(b, "text", "")}
                        for b in content_list
                    ],
                    "raw_text": raw_text,
                    "data": getattr(result, "structured_content", None),
                    "is_error": is_error,
                    "session_id": worker.session_id,
                }
            except Exception as e:
                logger.warning(f"MCP call_tool '{tool_name}' attempt {attempt + 1} failed: {e}")
                await self.session_manager.evict_session(config)
                if attempt == 1:
                    raise MCPConnectionError(f"Failed to execute MCP tool '{tool_name}': {e}") from e

        raise MCPConnectionError(f"Failed to execute MCP tool '{tool_name}' after retry.")

    async def disconnect(self, credentials: Any) -> None:
        """Terminates and clears the active session for this server."""
        try:
            config = parse_mcp_config(credentials)
            await self.session_manager.close_session(config)
        except Exception:
            pass


# Singleton instance
mcp_client = MCPClient()
