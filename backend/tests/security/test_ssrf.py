import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.security.ssrf import (
    validate_and_resolve_url,
    is_ip_allowed,
    SafeHTTPClient,
    SSRFError,
)

@pytest.mark.security
def test_ssrf_blocks_ipv4_private_addresses():
    """P1-1: Private IPv4 subnets (RFC 1918) must be blocked."""
    private_urls = [
        "http://10.0.0.1/admin",
        "http://172.16.5.10:8080/metrics",
        "http://192.168.1.1/",
    ]
    for url in private_urls:
        with pytest.raises(SSRFError, match="SSRF violation"):
            validate_and_resolve_url(url, allow_private=False)


@pytest.mark.security
def test_ssrf_blocks_loopback_addresses():
    """P1-1: Localhost and loopback ranges must be blocked."""
    loopback_urls = [
        "http://127.0.0.1:8000/api",
        "http://127.0.0.2/",
        "http://localhost:5000/",
    ]
    for url in loopback_urls:
        with pytest.raises(SSRFError):
            validate_and_resolve_url(url, allow_private=False)


@pytest.mark.security
def test_ssrf_blocks_cloud_metadata():
    """P1-1: Cloud metadata IP (169.254.169.254) and domains must be strictly blocked."""
    metadata_targets = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254:80/",
        "http://metadata.google.internal/computeMetadata/v1/",
    ]
    for url in metadata_targets:
        with pytest.raises(SSRFError):
            validate_and_resolve_url(url, allow_private=False)


@pytest.mark.security
def test_ssrf_blocks_link_local_and_ipv6_loopback():
    """P1-1: IPv6 loopback (::1) and link-local ranges must be blocked."""
    assert is_ip_allowed("::1", allow_private=False)[0] is False
    assert is_ip_allowed("169.254.1.1", allow_private=False)[0] is False
    assert is_ip_allowed("fe80::1", allow_private=False)[0] is False


@pytest.mark.security
def test_ssrf_allow_private_escape_hatch():
    """P1-1: allow_private=True permits private IPs for dev/test environments."""
    resolved_ip, orig_host, port = validate_and_resolve_url("http://127.0.0.1:8085/mcp", allow_private=True)
    assert resolved_ip == "127.0.0.1"
    assert port == 8085


@pytest.mark.security
def test_ssrf_blocks_dangerous_schemes():
    """P1-1: Non-HTTP(S) schemes such as file://, gopher://, ftp:// must be rejected."""
    dangerous = [
        "file:///etc/passwd",
        "gopher://127.0.0.1:70/",
        "ftp://example.com/test",
    ]
    for url in dangerous:
        with pytest.raises(SSRFError, match="Prohibited URL scheme"):
            validate_and_resolve_url(url)


@pytest.mark.security
def test_ssrf_blocks_mixed_dns_rebinding():
    """P1-1: Host resolving to both public and private IP must be rejected."""
    # Mock getaddrinfo returning one public IP and one private IP
    mock_addrinfo = [
        (2, 1, 6, "", ("93.184.216.34", 80)),
        (2, 1, 6, "", ("10.0.0.1", 80)),
    ]
    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with pytest.raises(SSRFError, match="SSRF violation"):
            validate_and_resolve_url("http://rebind.example.com", allow_private=False)


@pytest.mark.security
async def test_safe_http_client_redirect_limit():
    """P1-1: SafeHTTPClient must enforce maximum redirect hop limit (max 3)."""
    # Create redirect loop responses
    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "https://example.com/redirect"}

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=redirect_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.security.ssrf.validate_and_resolve_url", return_value=("93.184.216.34", "example.com", 443)), \
         patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(SSRFError, match="Exceeded maximum redirect limit"):
            await SafeHTTPClient.get("https://example.com/start", max_redirects=3)
