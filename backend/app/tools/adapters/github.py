import httpx
import json
from typing import Dict, Any, List, Optional
from app.tools.registry.base import BaseTool

MAX_CONTENT_CHARS = 8000

class GitHubTool(BaseTool):
    tool_type: str = "api"
    id: str = "github"
    name: str = "GitHub API"
    description: str = "Create and read GitHub issues."
    provides: List[str] = ["issue_create", "issue_read"]
    requires_connection: Optional[str] = "github"

    async def execute(self, capability: str, params: Dict[str, Any], credentials: Any = None) -> Dict[str, Any]:
        if not credentials:
            return {"error": "Missing GitHub credentials."}
        
        token = credentials if isinstance(credentials, str) else credentials.get("access_token")
        if not token:
            return {"error": "Missing access_token in credentials."}

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Relay-Agent/0.2"
        }

        if capability == "issue_create":
            repo = params.get("repository")  # format: "owner/repo"
            title = params.get("title")
            body = params.get("body", "")

            if not repo or not title:
                return {"error": "Missing 'repository' or 'title' parameters."}

            url = f"https://api.github.com/repos/{repo}/issues"
            payload = {"title": title, "body": body}

            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                    if resp.status_code == 201:
                        data = resp.json()
                        return {
                            "status": "success",
                            "issue_url": data.get("html_url"),
                            "issue_number": data.get("number")
                        }
                    else:
                        return {"error": f"GitHub API error {resp.status_code}: {resp.text[:200]}"}
                except Exception as e:
                    return {"error": f"Network error: {str(e)}"}
                    
        elif capability == "issue_read":
            repo = params.get("repository")
            issue_number = params.get("issue_number")
            
            if not repo or not issue_number:
                return {"error": "Missing 'repository' or 'issue_number'."}
                
            url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
            
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get(url, headers=headers, timeout=10.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        body_text = data.get("body") or ""
                        if len(body_text) > MAX_CONTENT_CHARS:
                            body_text = body_text[:MAX_CONTENT_CHARS] + "... [TRUNCATED]"
                        return {
                            "title": data.get("title"),
                            "state": data.get("state"),
                            "body": body_text
                        }
                    else:
                        return {"error": f"GitHub API error {resp.status_code}: {resp.text[:200]}"}
                except Exception as e:
                    return {"error": f"Network error: {str(e)}"}
                    
        return {"error": f"Unsupported capability '{capability}' for GitHub."}

    async def health_check(self, credentials: Any = None) -> tuple[bool, str]:
        if not credentials:
            return False, "No credentials provided."
        token = credentials if isinstance(credentials, str) else credentials.get("access_token")
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    "https://api.github.com/user", 
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "Relay-Agent/0.2"},
                    timeout=5.0
                )
                if resp.status_code == 200:
                    return True, "Connected to GitHub."
                return False, f"GitHub API error: {resp.status_code}"
            except Exception as e:
                return False, f"Connection failed: {str(e)}"

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
