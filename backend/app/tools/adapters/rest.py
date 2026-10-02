import httpx
import json
import urllib.parse
import ipaddress
import socket
from typing import Dict, Any, List, Optional, Tuple, Union
from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)

MAX_CONTENT_CHARS = 8000


class RestApiTool(BaseTool):
    tool_type: str = "api"
    id: str = "rest_connector"
    name: str = "REST API"
    description: str = "Generic REST API Connector."
    provides: List[str] = ["api_request"]
    requires_connection: Optional[str] = "rest_connector"
    required_permissions: List[str] = []

    def describe_actions(self) -> List[ActionSpec]:
        return [
            ActionSpec(
                action="api_request",
                capability_id="api_request",
                effect_class=EffectClass.NON_IDEMPOTENT_WRITE,
                reversible=False,
                target_param="url",
                required_permission=None,
                param_schema={
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
                        "url": {"type": "string", "description": "Target endpoint URL"},
                        "headers": {"type": "object"},
                        "payload": {"type": ["object", "string", "null"]}
                    },
                    "required": ["url"]
                },
                supports_idempotency_key=True
            )
        ]

    def _is_safe_url(self, url: str) -> bool:
        """Validate URL to prevent SSRF against internal/private endpoints."""
        from app.security.ssrf import validate_and_resolve_url, SSRFError
        try:
            validate_and_resolve_url(url)
            return True
        except SSRFError:
            return False
        except Exception:
            return False

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        ctx: ExecutionContext
    ) -> ToolResult:
        if action in ["api_request", "request"]:
            method = str(params.get("method", "GET")).upper()
            url = params.get("url")
            payload = params.get("payload")
            headers = dict(params.get("headers", {}))
            
            if not url:
                return ToolResult(status="error", error="Missing 'url' parameter.", side_effect_state="FAILED_NO_EFFECT")
                
            if method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                return ToolResult(status="error", error=f"Unsupported HTTP method: {method}", side_effect_state="FAILED_NO_EFFECT")
                
            if not self._is_safe_url(url):
                return ToolResult(status="error", error="URL blocked due to SSRF protection or invalid format.", side_effect_state="FAILED_NO_EFFECT")

            credentials = ctx.credentials if ctx else None
            if credentials:
                if isinstance(credentials, str):
                    headers["Authorization"] = f"Bearer {credentials}"
                elif isinstance(credentials, dict):
                    config_headers = credentials.get("headers", {})
                    headers.update(config_headers)
                    if "access_token" in credentials and "Authorization" not in headers:
                        headers["Authorization"] = f"Bearer {credentials['access_token']}"

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
                    
                    content = resp.text
                    truncated = False
                    if len(content) > MAX_CONTENT_CHARS:
                        content = content[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"
                        truncated = True
                        
                    return ToolResult(
                        status="success" if resp.status_code < 400 else "error",
                        data={
                            "status_code": resp.status_code,
                            "headers": dict(resp.headers),
                            "content": content,
                            "truncated": truncated
                        },
                        error=None if resp.status_code < 400 else f"HTTP error {resp.status_code}",
                        side_effect_state="CONFIRMED"
                    )
                except httpx.TooManyRedirects:
                    return ToolResult(status="error", error="Too many redirects.", side_effect_state="UNCERTAIN")
                except Exception as e:
                    return ToolResult(status="error", error=f"Network error: {str(e)}", side_effect_state="UNCERTAIN")
                    
        return ToolResult(status="error", error=f"Unsupported action '{action}' for REST API.", side_effect_state="FAILED_NO_EFFECT")

    async def health_check(self, credentials: Any = None) -> Tuple[bool, Optional[str]]:
        return True, "REST Connector configured."

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Union[ToolResult, Dict[str, Any]],
        ctx: ExecutionContext
    ) -> VerificationOutcome:
        err = result.get("error") if hasattr(result, "get") else None
        if err or (hasattr(result, "status") and result.status == "error"):
            return VerificationOutcome(
                result="failed",
                evidence={"error": err or getattr(result, "error", "Unknown error")},
                reason=err or "Execution failed"
            )
        return VerificationOutcome(
            result="passed",
            evidence={"status": "verified"},
            reason="REST API call completed successfully"
        )
