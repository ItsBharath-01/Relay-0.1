import httpx
import json
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


class GitHubTool(BaseTool):
    tool_type: str = "api"
    id: str = "github"
    name: str = "GitHub API"
    description: str = "Create and read GitHub issues."
    provides: List[str] = ["issue_create", "issue_read"]
    requires_connection: Optional[str] = "github"
    required_permissions: List[str] = ["repo"]

    def describe_actions(self) -> List[ActionSpec]:
        return [
            ActionSpec(
                action="issue_create",
                capability_id="issue_create",
                effect_class=EffectClass.NON_IDEMPOTENT_WRITE,
                reversible=False,
                target_param="repository",
                required_permission="repo",
                param_schema={
                    "type": "object",
                    "properties": {
                        "repository": {"type": "string", "description": "Repository in owner/repo format"},
                        "title": {"type": "string", "description": "Issue title"},
                        "body": {"type": "string", "description": "Issue body content"}
                    },
                    "required": ["repository", "title"]
                },
                supports_idempotency_key=True
            ),
            ActionSpec(
                action="issue_read",
                capability_id="issue_read",
                effect_class=EffectClass.READ_ONLY,
                reversible=False,
                target_param="repository",
                required_permission="repo",
                param_schema={
                    "type": "object",
                    "properties": {
                        "repository": {"type": "string", "description": "Repository in owner/repo format"},
                        "issue_number": {"type": "integer", "description": "Issue number"}
                    },
                    "required": ["repository", "issue_number"]
                },
                supports_idempotency_key=False
            )
        ]

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        ctx: ExecutionContext
    ) -> ToolResult:
        credentials = ctx.credentials if ctx else None
        if not credentials:
            return ToolResult(status="error", error="Missing GitHub credentials.", side_effect_state="FAILED_NO_EFFECT")
        
        token = credentials if isinstance(credentials, str) else (credentials.get("access_token") if isinstance(credentials, dict) else None)
        if not token:
            return ToolResult(status="error", error="Missing access_token in credentials.", side_effect_state="FAILED_NO_EFFECT")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Relay-Agent/0.2"
        }

        if action in ["issue_create", "create"]:
            repo = params.get("repository")  # format: "owner/repo"
            title = params.get("title")
            body = params.get("body", "")

            if not repo or not title:
                return ToolResult(status="error", error="Missing 'repository' or 'title' parameters.", side_effect_state="FAILED_NO_EFFECT")

            url = f"https://api.github.com/repos/{repo}/issues"
            payload = {"title": title, "body": body}

            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                    if resp.status_code == 201:
                        data = resp.json()
                        issue_num = data.get("number")
                        return ToolResult(
                            status="success",
                            data={
                                "issue_url": data.get("html_url"),
                                "issue_number": issue_num
                            },
                            external_ids=[str(issue_num)] if issue_num else [],
                            side_effect_state="CONFIRMED"
                        )
                    else:
                        return ToolResult(
                            status="error",
                            error=f"GitHub API error {resp.status_code}: {resp.text[:200]}",
                            side_effect_state="FAILED_NO_EFFECT"
                        )
                except Exception as e:
                    return ToolResult(status="error", error=f"Network error: {str(e)}", side_effect_state="UNCERTAIN")
                    
        elif action in ["issue_read", "read"]:
            repo = params.get("repository")
            issue_number = params.get("issue_number")
            
            if not repo or not issue_number:
                return ToolResult(status="error", error="Missing 'repository' or 'issue_number'.", side_effect_state="FAILED_NO_EFFECT")
                
            url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
            
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get(url, headers=headers, timeout=10.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        body_text = data.get("body") or ""
                        if len(body_text) > MAX_CONTENT_CHARS:
                            body_text = body_text[:MAX_CONTENT_CHARS] + "... [TRUNCATED]"
                        return ToolResult(
                            status="success",
                            data={
                                "title": data.get("title"),
                                "state": data.get("state"),
                                "body": body_text
                            },
                            side_effect_state="CONFIRMED"
                        )
                    else:
                        return ToolResult(
                            status="error",
                            error=f"GitHub API error {resp.status_code}: {resp.text[:200]}",
                            side_effect_state="FAILED_NO_EFFECT"
                        )
                except Exception as e:
                    return ToolResult(status="error", error=f"Network error: {str(e)}", side_effect_state="UNCERTAIN")
                    
        return ToolResult(status="error", error=f"Unsupported action '{action}' for GitHub.", side_effect_state="FAILED_NO_EFFECT")

    async def health_check(self, credentials: Any = None) -> Tuple[bool, Optional[str]]:
        if not credentials:
            return False, "No credentials provided."
        token = credentials if isinstance(credentials, str) else (credentials.get("access_token") if isinstance(credentials, dict) else None)
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    "https://api.github.com/user", 
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "Relay-Agent/0.2"},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    return True, "Connected to GitHub."
                return False, f"GitHub API error: {resp.status_code}"
            except Exception as e:
                err_msg = str(e) or type(e).__name__
                return False, f"Connection failed: {err_msg}"

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
            reason="GitHub action completed successfully"
        )
