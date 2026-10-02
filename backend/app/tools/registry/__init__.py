from typing import Dict, List, Optional
from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)

ALL_TOOLS: List[BaseTool] = []
TOOL_MAP: Dict[str, BaseTool] = {}
_INITIALIZED: bool = False


def _init_builtin_tools() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    from app.tools.adapters.web_search import WebSearchTool
    from app.tools.adapters.web_reader import WebReaderTool
    from app.tools.adapters.browser import PlaywrightBrowserTool
    from app.tools.adapters.google_calendar import GoogleCalendarTool
    from app.tools.adapters.gmail import GmailTool
    from app.tools.adapters.github import GitHubTool
    from app.tools.adapters.slack import SlackTool
    from app.tools.adapters.rest import RestApiTool
    from app.tools.adapters.filesystem import LocalFilesystemTool

    builtins = [
        WebSearchTool(),
        WebReaderTool(),
        PlaywrightBrowserTool(),
        GoogleCalendarTool(),
        GmailTool(),
        GitHubTool(),
        SlackTool(),
        RestApiTool(),
        LocalFilesystemTool(),
    ]

    for tool in builtins:
        if tool.id not in TOOL_MAP:
            ALL_TOOLS.append(tool)
            TOOL_MAP[tool.id] = tool

    _ensure_mcp_tool()


def _ensure_mcp_tool() -> None:
    if "mcp_tool" not in TOOL_MAP:
        try:
            from app.tools.adapters.mcp_adapter import MCPToolAdapter
            mcp_tool = MCPToolAdapter()
            if mcp_tool not in ALL_TOOLS:
                ALL_TOOLS.append(mcp_tool)
            TOOL_MAP["mcp_tool"] = mcp_tool
        except (ImportError, AttributeError):
            pass


def get_tool(tool_id: str) -> Optional[BaseTool]:
    """Retrieves tool instance by its ID."""
    _init_builtin_tools()
    return TOOL_MAP.get(tool_id)


def get_mcp_tool() -> BaseTool:
    """Returns the shared MCPToolAdapter instance."""
    _init_builtin_tools()
    return TOOL_MAP["mcp_tool"]


def get_tools_for_capability(capability_id: str) -> List[BaseTool]:
    """Finds all registered tools that provide a given capability."""
    _init_builtin_tools()
    return [t for t in ALL_TOOLS if capability_id in t.provides]


def get_all_tools() -> List[BaseTool]:
    """Returns all registered tool adapters."""
    _init_builtin_tools()
    return list(ALL_TOOLS)


def register_tool(tool: BaseTool) -> None:
    """Dynamically registers or updates a tool in the registry."""
    _init_builtin_tools()
    TOOL_MAP[tool.id] = tool
    if tool not in ALL_TOOLS:
        ALL_TOOLS.append(tool)


BUILTIN_TOOL_IDS = {
    "web_search_engine", "web_reader", "playwright_browser", "browser", "google_calendar",
    "gmail", "mcp_tool", "github", "slack", "rest_connector", "local_filesystem"
}


def unregister_tool(tool_id: str) -> None:
    """Removes a dynamic tool from the registry (never unregisters built-in tools)."""
    _init_builtin_tools()
    if tool_id in BUILTIN_TOOL_IDS:
        return
    if tool_id in TOOL_MAP:
        tool = TOOL_MAP.pop(tool_id)
        if tool in ALL_TOOLS:
            ALL_TOOLS.remove(tool)


def get_mcp_tools() -> List[BaseTool]:
    """Returns all registered MCP tools."""
    _init_builtin_tools()
    return [t for t in ALL_TOOLS if t.tool_type == "mcp"]
