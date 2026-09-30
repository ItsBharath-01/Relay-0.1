import httpx
from typing import Dict, Any, List, Optional
from app.tools.registry.base import BaseTool

class SlackTool(BaseTool):
    tool_type: str = "api"
    id: str = "slack"
    name: str = "Slack API"
    description: str = "Send messages to Slack channels."
    provides: List[str] = ["message_send"]
    requires_connection: Optional[str] = "slack"

    async def execute(self, capability: str, params: Dict[str, Any], credentials: Any = None) -> Dict[str, Any]:
        if not credentials:
            return {"error": "Missing Slack credentials."}
            
        token = credentials if isinstance(credentials, str) else credentials.get("access_token")
        if not token:
            return {"error": "Missing access_token in credentials."}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        if capability == "message_send":
            channel = params.get("channel")
            text = params.get("text")

            if not channel or not text:
                return {"error": "Missing 'channel' or 'text' parameters."}

            url = "https://slack.com/api/chat.postMessage"
            payload = {"channel": channel, "text": text}

            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            return {
                                "status": "success",
                                "channel": data.get("channel"),
                                "ts": data.get("ts")
                            }
                        else:
                            return {"error": f"Slack API error: {data.get('error')}"}
                    else:
                        return {"error": f"Slack HTTP error {resp.status_code}: {resp.text[:200]}"}
                except Exception as e:
                    return {"error": f"Network error: {str(e)}"}
                    
        return {"error": f"Unsupported capability '{capability}' for Slack."}

    async def health_check(self, credentials: Any = None) -> tuple[bool, str]:
        if not credentials:
            return False, "No credentials provided."
        token = credentials if isinstance(credentials, str) else credentials.get("access_token")
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        return True, f"Connected to Slack as {data.get('user')} on {data.get('team')}"
                    return False, f"Slack auth error: {data.get('error')}"
                return False, f"Slack API HTTP error: {resp.status_code}"
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
