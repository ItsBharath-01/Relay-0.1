from typing import Dict, List, Optional
from app.tools.registry.base import BaseTool
from app.tools.adapters.web_search import WebSearchTool
from app.tools.adapters.web_reader import WebReaderTool
from app.tools.adapters.browser import PlaywrightBrowserTool
from app.tools.adapters.google_calendar import GoogleCalendarTool
from app.tools.adapters.gmail import GmailTool
from app.tools.adapters.mcp_adapter import MCPToolAdapter
from app.tools.adapters.github import GitHubTool
from app.tools.adapters.slack import SlackTool
from app.tools.adapters.rest import RestApiTool
from app.tools.adapters.filesystem import LocalFilesystemTool

ALL_TOOLS: List[BaseTool] = [
    WebSearchTool(),
    WebReaderTool(),
    PlaywrightBrowserTool(),
    GoogleCalendarTool(),
    GmailTool(),
    MCPToolAdapter(),
    GitHubTool(),
    SlackTool(),
    RestApiTool(),
    LocalFilesystemTool(),
]

TOOL_MAP: Dict[str, BaseTool] = {tool.id: tool for tool in ALL_TOOLS}

def get_tool(tool_id: str) -> Optional[BaseTool]:
    """Retrieves tool instance by its ID."""
    return TOOL_MAP.get(tool_id)

def get_mcp_tool() -> MCPToolAdapter:
    """Returns the shared MCPToolAdapter instance."""
    return TOOL_MAP["mcp_tool"]  # type: ignore[return-value]

def get_tools_for_capability(capability_id: str) -> List[BaseTool]:
    """Finds all registered tools that provide a given capability."""
    return [t for t in ALL_TOOLS if capability_id in t.provides]

def get_all_tools() -> List[BaseTool]:
    """Returns all registered tool adapters."""
    return ALL_TOOLS
