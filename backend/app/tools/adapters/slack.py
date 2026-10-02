import httpx
from typing import Dict, Any, List, Optional, Tuple, Union
from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)


class SlackTool(BaseTool):
    tool_type: str = "api"
    id: str = "slack"
    name: str = "Slack API"
    description: str = "Send messages to Slack channels."
    provides: List[str] = ["message_send"]
    requires_connection: Optional[str] = "slack"
    required_permissions: List[str] = ["chat:write"]

    def describe_actions(self) -> List[ActionSpec]:
        return [
            ActionSpec(
                action="message_send",
                capability_id="message_send",
                effect_class=EffectClass.NON_IDEMPOTENT_WRITE,
                reversible=False,
                target_param="channel",
                required_permission="chat:write",
                param_schema={
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string", "description": "Channel ID or name"},
                        "text": {"type": "string", "description": "Message text"}
                    },
                    "required": ["channel", "text"]
                },
                supports_idempotency_key=True
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
            return ToolResult(status="error", error="Missing Slack credentials.", side_effect_state="FAILED_NO_EFFECT")
            
        token = credentials if isinstance(credentials, str) else (credentials.get("access_token") if isinstance(credentials, dict) else None)
        if not token:
            return ToolResult(status="error", error="Missing access_token in credentials.", side_effect_state="FAILED_NO_EFFECT")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        if action in ["message_send", "send"]:
            channel = params.get("channel")
            text = params.get("text")

            if not channel or not text:
                return ToolResult(status="error", error="Missing 'channel' or 'text' parameters.", side_effect_state="FAILED_NO_EFFECT")

            url = "https://slack.com/api/chat.postMessage"
            payload = {"channel": channel, "text": text}

            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            ts = data.get("ts")
                            return ToolResult(
                                status="success",
                                data={
                                    "channel": data.get("channel"),
                                    "ts": ts
                                },
                                external_ids=[ts] if ts else [],
                                side_effect_state="CONFIRMED"
                            )
                        else:
                            return ToolResult(
                                status="error",
                                error=f"Slack API error: {data.get('error')}",
                                side_effect_state="FAILED_NO_EFFECT"
                            )
                    else:
                        return ToolResult(
                            status="error",
                            error=f"Slack HTTP error {resp.status_code}: {resp.text[:200]}",
                            side_effect_state="FAILED_NO_EFFECT"
                        )
                except Exception as e:
                    return ToolResult(status="error", error=f"Network error: {str(e)}", side_effect_state="UNCERTAIN")
                    
        return ToolResult(status="error", error=f"Unsupported action '{action}' for Slack.", side_effect_state="FAILED_NO_EFFECT")

    async def health_check(self, credentials: Any = None) -> Tuple[bool, Optional[str]]:
        if not credentials:
            return False, "No credentials provided."
        token = credentials if isinstance(credentials, str) else (credentials.get("access_token") if isinstance(credentials, dict) else None)
        
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
            reason="Slack message sent successfully"
        )
