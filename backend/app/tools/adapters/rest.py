import httpx
import json
import urllib.parse
import ipaddress
import socket
from typing import Dict, Any, List, Optional
from app.tools.registry.base import BaseTool

MAX_CONTENT_CHARS = 8000

class RestApiTool(BaseTool):
    tool_type: str = "api"
    id: str = "rest_connector"
    name: str = "REST API"
    description: str = "Generic REST API Connector."
    provides: List[str] = ["api_request"]
    requires_connection: Optional[str] = "rest_connector"

    def _is_safe_url(self, url: str) -> bool:
        """Validate URL to prevent SSRF against internal/private endpoints."""
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ["http", "https"]:
                return False
                
            hostname = parsed.hostname
            if not hostname:
                return False
                
            # Block obviously bad hostnames
            if hostname in ["localhost", "127.0.0.1", "::1"]:
                return False
                
            # Block cloud metadata
            if hostname == "169.254.169.254":
                return False
                
            # Resolve DNS and block private IP ranges
            try:
                ip_info = socket.gethostbyname(hostname)
                ip = ipaddress.ip_address(ip_info)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return False
            except socket.gaierror:
                return False
                
            return True
        except Exception:
            return False

    async def execute(self, capability: str, params: Dict[str, Any], credentials: Any = None) -> Dict[str, Any]:
        if capability == "api_request":
            method = str(params.get("method", "GET")).upper()
            url = params.get("url")
            payload = params.get("payload")
            headers = params.get("headers", {})
            
            if not url:
                return {"error": "Missing 'url' parameter."}
                
            if method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                return {"error": f"Unsupported HTTP method: {method}"}
                
            if not self._is_safe_url(url):
                return {"error": "URL blocked due to SSRF protection or invalid format."}

            # Optional credentials merging
            if credentials:
                if isinstance(credentials, str):
                    headers["Authorization"] = f"Bearer {credentials}"
                elif isinstance(credentials, dict):
                    # Combine configured headers
                    config_headers = credentials.get("headers", {})
                    headers.update(config_headers)
                    if "access_token" in credentials and "Authorization" not in headers:
                        headers["Authorization"] = f"Bearer {credentials['access_token']}"

            # Make the request
            async with httpx.AsyncClient(follow_redirects=True, max_redirects=3) as client:
                try:
                    request_kwargs = {"timeout": 10.0}
                    if payload and method in ["POST", "PUT", "PATCH"]:
                        if isinstance(payload, str):
                            try:
                                payload = json.loads(payload)
                            except:
                                pass
                        
                        if isinstance(payload, dict) or isinstance(payload, list):
                            request_kwargs["json"] = payload
                        else:
                            request_kwargs["content"] = str(payload)

                    resp = await client.request(method, url, headers=headers, **request_kwargs)
                    
                    # Read content safely
                    content = resp.text
                    truncated = False
                    if len(content) > MAX_CONTENT_CHARS:
                        content = content[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"
                        truncated = True
                        
                    return {
                        "status_code": resp.status_code,
                        "headers": dict(resp.headers),
                        "content": content,
                        "truncated": truncated
                    }
                except httpx.TooManyRedirects:
                    return {"error": "Too many redirects."}
                except Exception as e:
                    return {"error": f"Network error: {str(e)}"}
                    
        return {"error": f"Unsupported capability '{capability}' for REST API."}

    async def health_check(self, credentials: Any = None) -> tuple[bool, str]:
        # A generic REST connector might just say true if configured properly.
        # If there's a specific health endpoint configured, we could check it.
        # But lacking that, assume true.
        return True, "REST Connector configured."

    async def verify(
        self,
        action: str,
        params: dict,
        result: dict,
        credentials=None
    ) -> tuple[bool, dict]:
        if "error" in result:
            return False, {"error": result["error"]}
        return True, {"status": "verified"}
