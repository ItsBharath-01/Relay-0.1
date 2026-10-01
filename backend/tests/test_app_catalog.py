"""Tests for the application catalog registry."""
import pytest
from app.catalog.apps import (
    APPLICATION_CATALOG,
    get_app,
    get_all_apps,
    get_apps_by_category,
    get_available_apps,
)


def test_catalog_has_all_expected_apps():
    expected_ids = {
        "gmail", "google_calendar", "slack", "github",
        "browser", "mcp", "rest_connector", "local_filesystem",
        "notion", "linear", "jira",
    }
    assert expected_ids.issubset(set(APPLICATION_CATALOG.keys()))


def test_available_apps_have_capabilities():
    for app in get_available_apps():
        assert app.capabilities, f"{app.app_id} is available but has no capabilities"


def test_coming_soon_apps_have_no_capabilities_and_unavailable():
    coming_soon = [a for a in get_all_apps() if not a.available]
    assert len(coming_soon) >= 3  # notion, linear, jira
    for app in coming_soon:
        assert app.capabilities == [], f"{app.app_id} is coming-soon but has capabilities"


def test_get_app_gmail():
    app = get_app("gmail")
    assert app is not None
    assert app.app_id == "gmail"
    assert app.name == "Gmail"
    assert "email_send" in app.capabilities
    assert app.connection_type == "oauth"
    assert app.available is True
    assert app.requires_credentials is True


def test_get_app_nonexistent_returns_none():
    assert get_app("nonexistent_app_xyz") is None


def test_get_apps_by_category_developer():
    dev_apps = get_apps_by_category("developer")
    app_ids = {a.app_id for a in dev_apps}
    assert "github" in app_ids
    assert "mcp" in app_ids


def test_get_apps_by_category_local():
    local_apps = get_apps_by_category("local")
    assert any(a.app_id == "local_filesystem" for a in local_apps)
    # local tools should not require credentials
    for app in local_apps:
        assert app.requires_credentials is False, f"{app.app_id} is local but requires credentials"


def test_get_all_apps_returns_all():
    apps = get_all_apps()
    assert len(apps) >= 11


def test_github_is_api_token():
    github = get_app("github")
    assert github.connection_type == "api_token"
    assert "issue_create" in github.capabilities
    assert "issue_read" in github.capabilities


def test_slack_is_api_token():
    slack = get_app("slack")
    assert slack.connection_type == "api_token"
    assert "message_send" in slack.capabilities


def test_browser_is_local_no_credentials():
    browser = get_app("browser")
    assert browser.connection_type == "local"
    assert browser.requires_credentials is False
    assert "browser_navigate" in browser.capabilities


def test_mcp_is_url_config():
    mcp = get_app("mcp")
    assert mcp.connection_type == "mcp"
    assert "mcp_call" in mcp.capabilities


def test_all_apps_have_required_fields():
    for app in get_all_apps():
        assert app.app_id
        assert app.name
        assert app.description
        assert app.icon_emoji
        assert app.category
        assert app.connection_type
        assert app.auth_label
        assert app.risk_profile in ("low", "medium", "high")
