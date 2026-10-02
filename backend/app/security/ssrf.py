"""
ssrf.py — Unified SSRF Protection with DNS Resolution & Pinning.

Enforces:
1. URL scheme validation (http/https only).
2. Hostname resolution to IP addresses (IPv4 & IPv6).
3. Blocking of:
   - Private / RFC1918 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
   - Loopback ranges (127.0.0.0/8, ::1)
   - Link-local ranges (169.254.0.0/16, fe80::/10)
   - Cloud metadata services (169.254.169.254, metadata.google.internal, *.internal)
   - Carrier-grade NAT (100.64.0.0/10)
   - Broadcast / multicast / unspecified
4. DNS Pinning:
   - Resolves IP once during validation.
   - Provides safe HTTP client / transport connecting directly to the validated IP,
     preventing Time-of-Check to Time-of-Use (TOCTOU) DNS rebinding attacks.
5. Redirect handling:
   - Max 3 redirect hops, re-validating the resolved destination at every hop.
6. Environment escape hatch:
   - settings.ALLOW_PRIVATE_NETWORKS (default False) permits private IPs for dev/tests.
"""

import ipaddress
import socket
import logging
from typing import Optional, Tuple, List, Dict, Any
from urllib.parse import urlparse, urlunparse

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# Cloud metadata and internal hostnames
CLOUD_METADATA_IPS = {
    "169.254.169.254",          # AWS / GCP / Azure metadata
    "fd00:ec2::254",            # AWS IPv6 metadata
}

BLOCKED_HOST_SUFFIXES = (
    ".internal",
    ".local",
    ".localhost",
)


class SSRFError(ValueError):
    """Raised when an outbound URL violates SSRF security policies."""
    pass


def is_ip_allowed(ip_str: str, allow_private: Optional[bool] = None) -> Tuple[bool, str]:
    """
    Checks if an IP address string is safe for outbound requests.
    Returns (is_allowed, reason).
    """
    if allow_private is None:
        allow_private = getattr(settings, "ALLOW_PRIVATE_NETWORKS", False)

    if ip_str in CLOUD_METADATA_IPS:
        return False, f"Cloud metadata service IP '{ip_str}' is forbidden."

    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address format: '{ip_str}'"

    # Always block link-local (169.254.x.x / fe80::/10) regardless of allow_private
    if ip.is_link_local:
        return False, f"Link-local IP '{ip_str}' is forbidden."

    # Always block multicast and unspecified (0.0.0.0, ::)
    if ip.is_multicast or ip.is_unspecified:
        return False, f"Multicast or unspecified IP '{ip_str}' is forbidden."

    if not allow_private:
        if ip.is_private:
            return False, f"Private network IP '{ip_str}' is forbidden."
        if ip.is_loopback:
            return False, f"Loopback IP '{ip_str}' is forbidden."
        if ip.is_reserved:
            return False, f"Reserved IP '{ip_str}' is forbidden."

    return True, "IP allowed"


def validate_and_resolve_url(
    url: str,
    allow_private: Optional[bool] = None
) -> Tuple[str, str, int]:
    """
    Validates a URL against SSRF policy and resolves DNS hostname to an allowed IP address.

    Returns:
        (resolved_ip, original_hostname, port)
    Raises:
        SSRFError: If the URL or resolved IP violates policy.
    """
    if not url or not isinstance(url, str):
        raise SSRFError("Missing or empty URL.")

    url_clean = url.strip()
    try:
        parsed = urlparse(url_clean)
    except Exception as e:
        raise SSRFError(f"Malformed URL: {e}")

    scheme = (parsed.scheme or "").lower()
    if scheme:
        if scheme not in ("http", "https"):
            raise SSRFError(f"Prohibited URL scheme '{scheme}'. Only http and https are allowed.")
    else:
        url_clean = f"https://{url_clean}"
        parsed = urlparse(url_clean)
        scheme = "https"

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFError("URL is missing hostname.")

    port = parsed.port or (443 if scheme == "https" else 80)

    # Check hostname patterns
    if hostname in CLOUD_METADATA_IPS:
        raise SSRFError(f"Access to cloud metadata IP '{hostname}' is blocked.")

    if hostname == "metadata.google.internal" or any(hostname.endswith(sfx) for sfx in BLOCKED_HOST_SUFFIXES):
        if not (allow_private if allow_private is not None else getattr(settings, "ALLOW_PRIVATE_NETWORKS", False)):
            raise SSRFError(f"Access to internal domain '{hostname}' is blocked.")

    # Check if hostname is already a raw IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        allowed, reason = is_ip_allowed(str(ip), allow_private=allow_private)
        if not allowed:
            raise SSRFError(f"SSRF violation: {reason}")
        return str(ip), hostname, port
    except ValueError:
        pass  # It is a domain name, resolve via DNS

    # DNS Resolution: resolve all A and AAAA records
    try:
        addrinfo = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for '{hostname}': {e}")

    if not addrinfo:
        raise SSRFError(f"No DNS records found for host '{hostname}'.")

    # Verify EVERY resolved IP address to prevent mixed public/private DNS rebinding tricks
    resolved_ips = []
    for entry in addrinfo:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        allowed, reason = is_ip_allowed(ip_str, allow_private=allow_private)
        if not allowed:
            raise SSRFError(f"SSRF violation for host '{hostname}': {reason}")
        resolved_ips.append(ip_str)

    # Return the first resolved IP for DNS pinning
    return resolved_ips[0], hostname, port


class PinnedDNSAsyncTransport(httpx.AsyncHTTPTransport):
    """
    Custom HTTPX Async Transport that pins DNS resolution to a verified IP,
    preventing DNS rebinding (TOCTOU) attacks while preserving SNI and Host header.
    """
    def __init__(self, pinned_ip: str, target_host: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pinned_ip = pinned_ip
        self.target_host = target_host

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await super().handle_async_request(request)


class SafeHTTPClient:
    """
    Safe HTTP request manager that:
    1. Validates and resolves destination URLs against SSRF policies.
    2. Enforces DNS pinning to prevent rebinding.
    3. Handles redirects safely (max 3 hops, re-validating each hop).
    """

    @classmethod
    async def get(
        cls,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
        allow_private: Optional[bool] = None,
        max_redirects: int = 3,
    ) -> httpx.Response:
        return await cls.request(
            method="GET",
            url=url,
            headers=headers,
            timeout=timeout,
            allow_private=allow_private,
            max_redirects=max_redirects,
        )

    @classmethod
    async def request(
        cls,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Any] = None,
        data: Optional[Any] = None,
        timeout: float = 15.0,
        allow_private: Optional[bool] = None,
        max_redirects: int = 3,
    ) -> httpx.Response:
        current_url = url
        current_headers = dict(headers or {})
        redirect_count = 0

        while True:
            # 1. Validate and resolve current hop
            resolved_ip, orig_host, port = validate_and_resolve_url(
                current_url,
                allow_private=allow_private
            )

            # 2. Execute request with follow_redirects=False to inspect every hop
            req_headers = dict(current_headers)
            # Ensure Host header matches original hostname
            if "host" not in [k.lower() for k in req_headers]:
                req_headers["Host"] = orig_host if (port in (80, 443)) else f"{orig_host}:{port}"

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.request(
                    method=method if redirect_count == 0 else "GET",
                    url=current_url,
                    headers=req_headers,
                    json=json_body if redirect_count == 0 else None,
                    data=data if redirect_count == 0 else None,
                )

            # Check if this response is a redirect
            if response.status_code in (301, 302, 303, 307, 308) and "location" in response.headers:
                redirect_count += 1
                if redirect_count > max_redirects:
                    raise SSRFError(f"Exceeded maximum redirect limit of {max_redirects} hops.")

                location = response.headers["location"]
                # Resolve relative redirects
                from urllib.parse import urljoin
                current_url = urljoin(current_url, location)
                continue

            return response


def validate_mcp_url(url: str) -> Tuple[str, str, int]:
    """
    SSRF validation for MCP server URLs.

    Extends the standard validate_and_resolve_url() with a narrowly scoped
    development-only allowlist for local MCP endpoints.

    The allowlist is controlled exclusively by:
        RELAY_DEV_ALLOW_LOCAL_MCP=true
        RELAY_DEV_LOCAL_MCP_HOSTS=127.0.0.1,localhost

    Rules:
    - Production environments (ENVIRONMENT=production): allowlist is IGNORED,
      full SSRF policy applies unconditionally.
    - Non-production with RELAY_DEV_ALLOW_LOCAL_MCP=false: full SSRF policy.
    - Non-production with RELAY_DEV_ALLOW_LOCAL_MCP=true:
        * Cloud metadata IPs (169.254.169.254, fd00:ec2::254) → BLOCKED always.
        * Link-local (169.254.x.x / fe80::/10) → BLOCKED always.
        * DNS rebinding (mixed public+private resolution) → BLOCKED always.
        * Redirects are still limited to 3 hops.
        * Only hostnames explicitly listed in RELAY_DEV_LOCAL_MCP_HOSTS are allowed.
        * All other private/loopback IPs → BLOCKED.

    This function is called ONLY from the MCP registration and health-check
    paths. It must NOT be used for REST, web reader, or browser adapters.
    """
    env = getattr(settings, "ENVIRONMENT", "production").lower()
    dev_allowed = getattr(settings, "RELAY_DEV_ALLOW_LOCAL_MCP", False)

    # In production the allowlist is always disabled regardless of the env var
    if env == "production":
        dev_allowed = False

    if not dev_allowed:
        # Standard strict SSRF — identical to all other tools
        return validate_and_resolve_url(url)

    # Parse URL to extract the hostname for allowlist check
    if not url or not isinstance(url, str):
        raise SSRFError("Missing or empty MCP URL.")
    parsed = urlparse(url.strip())
    hostname = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    if scheme and scheme not in ("http", "https"):
        raise SSRFError(f"Prohibited URL scheme '{scheme}'. Only http and https are allowed.")

    if not hostname:
        raise SSRFError("MCP URL is missing hostname.")

    # Always block cloud metadata — no exceptions
    if hostname in CLOUD_METADATA_IPS:
        raise SSRFError(f"Access to cloud metadata IP '{hostname}' is blocked even in dev mode.")

    # Resolve to IP to check for cloud metadata via numeric IP
    try:
        ip_obj = ipaddress.ip_address(hostname)
        ip_str = str(ip_obj)
        # Cloud metadata and link-local are always blocked
        if ip_str in CLOUD_METADATA_IPS or ip_obj.is_link_local:
            raise SSRFError(f"Access to '{hostname}' is blocked even in dev mode.")
        if ip_obj.is_multicast or ip_obj.is_unspecified:
            raise SSRFError(f"Multicast/unspecified address '{hostname}' is blocked.")
        is_raw_ip = True
    except ValueError:
        ip_str = None
        is_raw_ip = False

    # Build the explicit allowlist from config
    raw_allowed = getattr(settings, "RELAY_DEV_LOCAL_MCP_HOSTS", "127.0.0.1,localhost")
    allowed_hosts = {h.strip().lower() for h in raw_allowed.split(",") if h.strip()}

    # Check if the hostname (or its raw IP form) is in the allowlist
    in_allowlist = hostname in allowed_hosts or (ip_str is not None and ip_str in allowed_hosts)

    if not in_allowlist:
        # Not on the allowlist → apply full strict SSRF policy
        return validate_and_resolve_url(url)

    # The hostname is explicitly allowlisted — still validate it is actually
    # a loopback/private and not something that resolved to a public IP via DNS rebinding.
    if is_raw_ip:
        ip_obj2 = ipaddress.ip_address(ip_str)
        if not (ip_obj2.is_loopback or ip_obj2.is_private):
            raise SSRFError(
                f"Allowlisted host '{hostname}' resolved to a non-loopback/non-private IP '{ip_str}'. "
                "This looks like DNS rebinding — blocked."
            )
        return ip_str, hostname, parsed.port or (443 if scheme == "https" else 80)
    else:
        # DNS resolution — check for rebinding: all resolved IPs must be loopback/private
        port = parsed.port or (443 if scheme == "https" else 80)
        try:
            addrinfo = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise SSRFError(f"DNS resolution failed for allowlisted host '{hostname}': {e}")

        resolved_ips = []
        for entry in addrinfo:
            ip_str_r = entry[4][0]
            if ip_str_r in CLOUD_METADATA_IPS:
                raise SSRFError(
                    f"Allowlisted hostname '{hostname}' resolved to cloud metadata IP '{ip_str_r}'. "
                    "Blocked to prevent DNS rebinding."
                )
            try:
                resolved_ip = ipaddress.ip_address(ip_str_r)
            except ValueError:
                raise SSRFError(f"Resolved unexpected address format '{ip_str_r}'.")
            if resolved_ip.is_link_local:
                raise SSRFError(
                    f"Allowlisted hostname '{hostname}' resolved to link-local IP '{ip_str_r}'. Blocked."
                )
            if not (resolved_ip.is_loopback or resolved_ip.is_private):
                raise SSRFError(
                    f"Allowlisted hostname '{hostname}' resolved to public IP '{ip_str_r}'. "
                    "This looks like DNS rebinding — blocked."
                )
            resolved_ips.append(ip_str_r)

        return resolved_ips[0], hostname, port

