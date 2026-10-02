"""
test_mcp_ssrf_local_allowlist.py — Regression tests for the narrowly scoped
MCP local development SSRF allowlist.

Tests:
  A. Production + 127.0.0.1 MCP → BLOCKED
  B. Development + explicit local MCP allowlist → ALLOWED
  C. Development + non-allowlisted private IP → BLOCKED
  D. Development + cloud metadata address → BLOCKED
  E. Development + arbitrary localhost REST URL (not MCP path) → must NOT bypass
     (REST/web tools still use validate_and_resolve_url, no allowlist)
  F. Local MCP registration (validate_mcp_config) succeeds when explicitly allowed
  G. validate_and_resolve_url still blocks localhost even in dev mode (no regression)
  H. Development + link-local IP → BLOCKED even with allowlist enabled
"""

import pytest
from unittest.mock import patch

from app.security.ssrf import validate_mcp_url, validate_and_resolve_url, SSRFError
from app.tools.adapters.mcp_client import validate_mcp_config


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mcp_dev_settings(**overrides):
    """Produce a patch dict for settings relevant to validate_mcp_url."""
    base = {
        "ENVIRONMENT": "development",
        "RELAY_DEV_ALLOW_LOCAL_MCP": True,
        "RELAY_DEV_LOCAL_MCP_HOSTS": "127.0.0.1,localhost",
        "ALLOW_PRIVATE_NETWORKS": False,
    }
    base.update(overrides)
    return base


def _patch_settings(**kw):
    """Context manager that patches app.security.ssrf.settings attributes."""
    patches = {f"app.security.ssrf.settings.{k}": v for k, v in kw.items()}
    # Also patch app.core.config.settings in case mcp_client reads it directly
    patches.update({f"app.core.config.settings.{k}": v for k, v in kw.items()})
    return [patch(target, new=value) for target, new in patches.items()]


# ─────────────────────────────────────────────────────────────────────────────
# A. Production + 127.0.0.1 MCP → BLOCKED
# ─────────────────────────────────────────────────────────────────────────────

def test_A_production_blocks_local_mcp():
    """
    Even if RELAY_DEV_ALLOW_LOCAL_MCP is set, production must reject 127.0.0.1.
    """
    with patch("app.security.ssrf.settings.ENVIRONMENT", "production"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError, match="(Loopback|Private|SSRF)"):
            validate_mcp_url("http://127.0.0.1:8085/mcp")


# ─────────────────────────────────────────────────────────────────────────────
# B. Development + explicit local MCP allowlist → ALLOWED
# ─────────────────────────────────────────────────────────────────────────────

def test_B_dev_allowlisted_local_mcp_passes():
    """
    In development with RELAY_DEV_ALLOW_LOCAL_MCP=True and 127.0.0.1 on the
    allowlist, validate_mcp_url must succeed.
    """
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        ip, host, port = validate_mcp_url("http://127.0.0.1:8085/mcp")
        assert ip == "127.0.0.1"
        assert port == 8085


# ─────────────────────────────────────────────────────────────────────────────
# C. Development + non-allowlisted private IP → BLOCKED
# ─────────────────────────────────────────────────────────────────────────────

def test_C_dev_non_allowlisted_private_ip_blocked():
    """
    10.0.0.1 is NOT on the allowlist — must be rejected.
    """
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError, match="(Private|SSRF)"):
            validate_mcp_url("http://10.0.0.1:8080/mcp")


def test_C2_dev_192_168_blocked():
    """192.168.x.x is NOT on the allowlist."""
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError, match="(Private|SSRF)"):
            validate_mcp_url("http://192.168.1.100:8085/mcp")


# ─────────────────────────────────────────────────────────────────────────────
# D. Development + cloud metadata address → BLOCKED even with allowlist
# ─────────────────────────────────────────────────────────────────────────────

def test_D_dev_cloud_metadata_always_blocked():
    """
    169.254.169.254 must be blocked unconditionally regardless of allowlist.
    """
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost,169.254.169.254"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError):
            validate_mcp_url("http://169.254.169.254/latest/meta-data")


# ─────────────────────────────────────────────────────────────────────────────
# E. validate_and_resolve_url (used by REST/web reader) still blocks localhost
# ─────────────────────────────────────────────────────────────────────────────

def test_E_strict_ssrf_unaffected_by_mcp_allowlist():
    """
    validate_and_resolve_url (used by all non-MCP tools) must NOT be affected
    by RELAY_DEV_ALLOW_LOCAL_MCP. It has its own allow_private=False logic.
    """
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        # REST tool path — still blocked
        with pytest.raises(SSRFError, match="(Loopback|Private|SSRF)"):
            validate_and_resolve_url("http://127.0.0.1:8085/some-rest-endpoint")


# ─────────────────────────────────────────────────────────────────────────────
# F. validate_mcp_config succeeds for local MCP when allowed
# ─────────────────────────────────────────────────────────────────────────────

def test_F_validate_mcp_config_local_succeeds_when_allowed():
    """
    validate_mcp_config (called during MCP registration) must not raise when
    RELAY_DEV_ALLOW_LOCAL_MCP=true and the URL is 127.0.0.1.
    """
    config = {
        "transport": "streamable_http",
        "server_url": "http://127.0.0.1:8085/mcp",
    }
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        # Must not raise
        validate_mcp_config(config)


def test_F2_validate_mcp_config_local_blocked_when_not_allowed():
    """
    validate_mcp_config blocks 127.0.0.1 when RELAY_DEV_ALLOW_LOCAL_MCP=false.
    """
    config = {
        "transport": "streamable_http",
        "server_url": "http://127.0.0.1:8085/mcp",
    }
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", False), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(ValueError, match="SSRF"):
            validate_mcp_config(config)


# ─────────────────────────────────────────────────────────────────────────────
# G. validate_and_resolve_url baseline — existing SSRF tests not regressed
# ─────────────────────────────────────────────────────────────────────────────

def test_G_baseline_ssrf_still_blocks_loopback():
    with patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError):
            validate_and_resolve_url("http://127.0.0.1/anything")


def test_G2_baseline_ssrf_still_blocks_private():
    with patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError):
            validate_and_resolve_url("http://192.168.0.1/anything")


def test_G3_baseline_ssrf_public_ip_passes():
    # A well-known public IP (8.8.8.8) should pass the URL validation stage
    with patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        ip, host, port = validate_and_resolve_url("http://8.8.8.8/test")
        assert ip == "8.8.8.8"


# ─────────────────────────────────────────────────────────────────────────────
# H. Development + link-local IP → BLOCKED even with allowlist
# ─────────────────────────────────────────────────────────────────────────────

def test_H_dev_link_local_always_blocked():
    """169.254.x.x (link-local) is blocked unconditionally in all modes."""
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost,169.254.1.1"), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError):
            validate_mcp_url("http://169.254.1.1:8085/mcp")


# ─────────────────────────────────────────────────────────────────────────────
# I. Empty allowlist in dev mode → all private IPs blocked
# ─────────────────────────────────────────────────────────────────────────────

def test_I_empty_allowlist_blocks_localhost():
    """When allowlist is empty, even 127.0.0.1 is blocked in dev mode."""
    with patch("app.security.ssrf.settings.ENVIRONMENT", "development"), \
         patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", True), \
         patch("app.security.ssrf.settings.RELAY_DEV_LOCAL_MCP_HOSTS", ""), \
         patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
        with pytest.raises(SSRFError):
            validate_mcp_url("http://127.0.0.1:8085/mcp")


# ─────────────────────────────────────────────────────────────────────────────
# J. Public MCP endpoint passes in all modes (no regression)
# ─────────────────────────────────────────────────────────────────────────────

def test_J_public_mcp_endpoint_always_allowed():
    """A public MCP server URL must pass in both dev and production."""
    for env in ("development", "production"):
        with patch("app.security.ssrf.settings.ENVIRONMENT", env), \
             patch("app.security.ssrf.settings.RELAY_DEV_ALLOW_LOCAL_MCP", False), \
             patch("app.security.ssrf.settings.ALLOW_PRIVATE_NETWORKS", False):
            ip, host, port = validate_mcp_url("http://8.8.8.8/mcp")
            assert ip == "8.8.8.8"
