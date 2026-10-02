"""
apps.py — Application Catalog for Relay 0.2

Static registry of all supported integrations. The frontend reads this
via GET /catalog — no app-specific logic lives in the planner or executor.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel


class AppDefinition(BaseModel):
    app_id: str
    name: str
    description: str
    icon_emoji: str
    category: str           # productivity | communication | developer | browser | local | api
    connection_type: str    # oauth | api_token | url_config | local | mcp
    auth_label: str         # human-readable credential label
    auth_instructions: str  # one-sentence setup instruction shown to user
    requires_credentials: bool
    capabilities: List[str]  # capability IDs this app provides
    risk_profile: str        # low | medium | high
    available: bool          # False → "Coming soon"
    docs_url: Optional[str] = None


APPLICATION_CATALOG: Dict[str, AppDefinition] = {
    "gmail": AppDefinition(
        app_id="gmail",
        name="Gmail",
        description="Read, draft, and send emails from your Google account.",
        icon_emoji="📧",
        category="productivity",
        connection_type="oauth",
        auth_label="Google Account",
        auth_instructions="Authorize via Google OAuth to grant Relay access to your Gmail.",
        requires_credentials=True,
        capabilities=["email_read", "email_draft", "email_send"],
        risk_profile="high",
        available=True,
        docs_url="https://developers.google.com/gmail/api",
    ),
    "google_calendar": AppDefinition(
        app_id="google_calendar",
        name="Google Calendar",
        description="Read, create, and delete calendar events in Google Calendar.",
        icon_emoji="📅",
        category="productivity",
        connection_type="oauth",
        auth_label="Google Account",
        auth_instructions="Authorize via Google OAuth to grant Relay access to your Calendar.",
        requires_credentials=True,
        capabilities=["calendar_read", "calendar_create", "calendar_delete"],
        risk_profile="medium",
        available=True,
        docs_url="https://developers.google.com/calendar",
    ),
    "slack": AppDefinition(
        app_id="slack",
        name="Slack",
        description="Send messages to Slack channels and workspaces.",
        icon_emoji="💬",
        category="communication",
        connection_type="api_token",
        auth_label="Slack Bot Token",
        auth_instructions="Create a Slack app, add the chat:write scope, install it, and paste the Bot User OAuth Token (xoxb-...).",
        requires_credentials=True,
        capabilities=["message_send"],
        risk_profile="high",
        available=True,
        docs_url="https://api.slack.com/authentication/token-types",
    ),
    "github": AppDefinition(
        app_id="github",
        name="GitHub",
        description="Create and read GitHub issues in your repositories.",
        icon_emoji="🐙",
        category="developer",
        connection_type="api_token",
        auth_label="Personal Access Token",
        auth_instructions="Generate a GitHub Personal Access Token with the 'repo' scope and paste it here.",
        requires_credentials=True,
        capabilities=["issue_create", "issue_read"],
        risk_profile="medium",
        available=True,
        docs_url="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
    ),
    "browser": AppDefinition(
        app_id="browser",
        name="Headless Browser",
        description="Navigate websites, fill forms, and scrape dynamic pages via Playwright.",
        icon_emoji="🌐",
        category="browser",
        connection_type="local",
        auth_label="Local Tool",
        auth_instructions="No credentials needed — Playwright runs locally on the Relay server.",
        requires_credentials=False,
        capabilities=["browser_navigate", "web_read"],
        risk_profile="medium",
        available=True,
    ),
    "mcp": AppDefinition(
        app_id="mcp",
        name="MCP Server",
        description="Connect any Model Context Protocol server to expose its tools to Relay.",
        icon_emoji="🤖",
        category="developer",
        connection_type="mcp",
        auth_label="Endpoint URL or stdio command",
        auth_instructions="Connect via Streamable HTTP URL or local stdio command (e.g. python -m server).",
        requires_credentials=True,
        capabilities=["mcp_call"],
        risk_profile="medium",
        available=True,
        docs_url="https://modelcontextprotocol.io",
    ),
    "rest_connector": AppDefinition(
        app_id="rest_connector",
        name="REST API",
        description="Call any permitted external REST API with configurable auth and endpoints.",
        icon_emoji="🔌",
        category="api",
        connection_type="url_config",
        auth_label="API Token / Key",
        auth_instructions="Enter the base URL and optional API key or bearer token for your REST endpoint.",
        requires_credentials=True,
        capabilities=["api_request"],
        risk_profile="medium",
        available=True,
    ),
    "local_filesystem": AppDefinition(
        app_id="local_filesystem",
        name="Local Files",
        description="Read and write files within the configured sandboxed workspace directory.",
        icon_emoji="📁",
        category="local",
        connection_type="local",
        auth_label="Local Tool",
        auth_instructions="No credentials needed — files are accessed within the server's configured RELAY_WORKSPACE_ROOT.",
        requires_credentials=False,
        capabilities=["file_read", "file_write"],
        risk_profile="medium",
        available=True,
    ),
    # ── Coming soon ────────────────────────────────────────────────────────────
    "notion": AppDefinition(
        app_id="notion",
        name="Notion",
        description="Read and write Notion pages and databases.",
        icon_emoji="📝",
        category="productivity",
        connection_type="oauth",
        auth_label="Notion Account",
        auth_instructions="Coming soon — Notion OAuth integration is not yet available.",
        requires_credentials=True,
        capabilities=[],
        risk_profile="medium",
        available=False,
    ),
    "linear": AppDefinition(
        app_id="linear",
        name="Linear",
        description="Create and manage Linear issues and projects.",
        icon_emoji="📋",
        category="developer",
        connection_type="api_token",
        auth_label="Linear API Key",
        auth_instructions="Coming soon — Linear integration is not yet available.",
        requires_credentials=True,
        capabilities=[],
        risk_profile="medium",
        available=False,
    ),
    "jira": AppDefinition(
        app_id="jira",
        name="Jira",
        description="Create and track Jira issues and sprints.",
        icon_emoji="🎯",
        category="developer",
        connection_type="oauth",
        auth_label="Atlassian Account",
        auth_instructions="Coming soon — Jira OAuth integration is not yet available.",
        requires_credentials=True,
        capabilities=[],
        risk_profile="medium",
        available=False,
    ),
}


def get_app(app_id: str) -> Optional[AppDefinition]:
    """Returns app definition by ID, or None if not found."""
    return APPLICATION_CATALOG.get(app_id)


def get_all_apps() -> List[AppDefinition]:
    """Returns all apps in the catalog (available and coming soon)."""
    return list(APPLICATION_CATALOG.values())


def get_apps_by_category(category: str) -> List[AppDefinition]:
    """Returns all apps in a given category."""
    return [a for a in APPLICATION_CATALOG.values() if a.category == category]


def get_available_apps() -> List[AppDefinition]:
    """Returns only apps with real connectors."""
    return [a for a in APPLICATION_CATALOG.values() if a.available]
