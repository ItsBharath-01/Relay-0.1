from typing import Dict, List, Optional
from pydantic import BaseModel

class Capability(BaseModel):
    id: str
    label: str
    category: str  # "browser" | "api" | "mcp" | "connector"
    default_risk: str  # "low" | "medium" | "high" | "critical"
    description: str

CAPABILITY_REGISTRY: Dict[str, Capability] = {
    "web_search": Capability(
        id="web_search",
        label="Web Search",
        category="api",
        default_risk="low",
        description="Search public internet queries and retrieve ranked search results."
    ),
    "web_read": Capability(
        id="web_read",
        label="Web Page Reading",
        category="api",
        default_risk="low",
        description="Fetch and extract text content and articles from web URLs."
    ),
    "browser_navigate": Capability(
        id="browser_navigate",
        label="Headless Browser Navigation",
        category="browser",
        default_risk="medium",
        description="Interact with web applications, fill forms, and scrape dynamic pages via Playwright."
    ),
    "calendar_read": Capability(
        id="calendar_read",
        label="Read Calendar",
        category="api",
        default_risk="low",
        description="Check user availability and inspect scheduled calendar events."
    ),
    "calendar_create": Capability(
        id="calendar_create",
        label="Schedule Calendar Event",
        category="api",
        default_risk="medium",
        description="Create meetings, invites, and calendar events with participants."
    ),
    "calendar_delete": Capability(
        id="calendar_delete",
        label="Delete Calendar Event",
        category="api",
        default_risk="high",
        description="Remove or cancel scheduled calendar events."
    ),
    "email_read": Capability(
        id="email_read",
        label="Read Emails",
        category="api",
        default_risk="low",
        description="Read messages, search inbox, and review email threads."
    ),
    "email_draft": Capability(
        id="email_draft",
        label="Draft Email",
        category="api",
        default_risk="low",
        description="Compose message drafts without sending."
    ),
    "email_send": Capability(
        id="email_send",
        label="Send Email",
        category="api",
        default_risk="high",
        description="Send outgoing emails to external contacts."
    ),
    "message_send": Capability(
        id="message_send",
        label="Send Message",
        category="api",
        default_risk="high",
        description="Send instant messages into Slack or team channels."
    ),
    "issue_create": Capability(
        id="issue_create",
        label="Create Issue",
        category="api",
        default_risk="medium",
        description="Create tasks, bugs, or issues in GitHub or task managers."
    ),
    "document_summarize": Capability(
        id="document_summarize",
        label="Document Summarization",
        category="api",
        default_risk="low",
        description="Analyze, summarize, and extract key action items from documents."
    ),
    "file_read": Capability(
        id="file_read",
        label="Read Attached File",
        category="connector",
        default_risk="low",
        description="Read and parse user-uploaded files or context documents."
    ),
    "file_write": Capability(
        id="file_write",
        label="Write Workspace File",
        category="connector",
        default_risk="medium",
        description="Create or overwrite files within the configured local workspace sandbox."
    ),
    "api_request": Capability(
        id="api_request",
        label="REST API Request",
        category="connector",
        default_risk="medium",
        description="Execute HTTP GET/POST requests against configured REST endpoints."
    ),
    "mcp_call": Capability(
        id="mcp_call",
        label="MCP Server Tool",
        category="mcp",
        default_risk="medium",
        description="Invoke tools exposed by user-connected Model Context Protocol servers."
    ),
}

def get_all_capabilities() -> List[Capability]:
    """Returns all registered capabilities."""
    return list(CAPABILITY_REGISTRY.values())

def get_capability(cap_id: str) -> Optional[Capability]:
    """Retrieves a capability by id."""
    return CAPABILITY_REGISTRY.get(cap_id)

def get_valid_capability_ids() -> List[str]:
    """Returns the list of valid capability IDs."""
    return list(CAPABILITY_REGISTRY.keys())

def register_capability(cap: Capability) -> None:
    """Registers or updates a capability dynamically."""
    CAPABILITY_REGISTRY[cap.id] = cap

def unregister_capability(cap_id: str) -> None:
    """Unregisters a capability if present."""
    CAPABILITY_REGISTRY.pop(cap_id, None)

