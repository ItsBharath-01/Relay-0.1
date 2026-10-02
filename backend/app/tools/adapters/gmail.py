import json
import base64
from email.mime.text import MIMEText
from typing import Dict, Any, Optional, Tuple, List, Union
import httpx

from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)


class GmailTool(BaseTool):
    id = "gmail"
    name = "Gmail"
    tool_type = "api"
    provides = ["email_read", "email_draft", "email_send"]
    requires_connection = "gmail"
    required_permissions = ["read", "draft", "send"]

    def describe_actions(self) -> List[ActionSpec]:
        return [
            ActionSpec(
                action="email_read",
                capability_id="email_read",
                effect_class=EffectClass.READ_ONLY,
                reversible=False,
                target_param="query",
                required_permission="gmail.readonly",
                param_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Gmail search query (e.g. from:someone)"},
                        "max_results": {"type": "integer", "default": 10}
                    }
                },
                supports_idempotency_key=False
            ),
            ActionSpec(
                action="email_draft",
                capability_id="email_draft",
                effect_class=EffectClass.NON_IDEMPOTENT_WRITE,
                reversible=True,
                target_param="to",
                required_permission="gmail.compose",
                param_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "recipient": {"type": "string", "description": "Alternative recipient email"},
                        "subject": {"type": "string", "description": "Subject line"},
                        "body": {"type": "string", "description": "Email body content"},
                        "content": {"type": "string", "description": "Alternative body parameter"}
                    }
                },
                supports_idempotency_key=True
            ),
            ActionSpec(
                action="email_send",
                capability_id="email_send",
                effect_class=EffectClass.IRREVERSIBLE,
                reversible=False,
                target_param="to",
                required_permission="gmail.send",
                param_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "recipient": {"type": "string", "description": "Alternative recipient email"},
                        "subject": {"type": "string", "description": "Subject line"},
                        "body": {"type": "string", "description": "Email body content"},
                        "content": {"type": "string", "description": "Alternative body parameter"}
                    }
                },
                supports_idempotency_key=True
            )
        ]

    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        if not credentials:
            return False, "Gmail is not connected. Connect via OAuth in Connections."
        try:
            cred_dict = json.loads(credentials) if isinstance(credentials, str) else credentials
            token = cred_dict.get("access_token")
            if not token:
                return False, "Missing OAuth access token"

            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=headers)
                if res.status_code == 200:
                    profile = res.json()
                    return True, f"Gmail connected ({profile.get('emailAddress')})"
                elif res.status_code == 401:
                    return False, "Token expired or revoked. Reconnection needed."
                return False, f"Gmail API returned HTTP {res.status_code}"
        except Exception as e:
            return False, f"Connection check failed: {str(e)}"

    def _create_message(self, to: str, subject: str, message_text: str) -> dict:
        message = MIMEText(message_text)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw}

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        ctx: ExecutionContext
    ) -> ToolResult:
        credentials = ctx.credentials if ctx else None
        if not credentials:
            raise PermissionError("Gmail is not connected. User must connect Gmail in Connections first.")

        cred_dict = json.loads(credentials) if isinstance(credentials, str) else credentials
        token = cred_dict.get("access_token") if isinstance(cred_dict, dict) else None
        if not token:
            raise PermissionError("Invalid or missing Google access token.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            if action in ["email_read", "read"]:
                url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
                q = params.get("query", "")
                q_params = {"maxResults": 10}
                if q:
                    q_params["q"] = q
                res = await client.get(url, headers=headers, params=q_params)
                if res.status_code != 200:
                    raise RuntimeError(f"Gmail read failed: {res.text}")
                messages = res.json().get("messages", [])
                return ToolResult(
                    status="success",
                    data={"action": "email_read", "count": len(messages), "messages": messages},
                    side_effect_state="CONFIRMED"
                )

            elif action in ["email_draft", "draft"]:
                to = params.get("to") or params.get("recipient", "")
                subject = params.get("subject", "Draft from Relay")
                body = params.get("body") or params.get("content", "")
                
                raw_msg = self._create_message(to, subject, body)
                draft_body = {"message": raw_msg}

                url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
                res = await client.post(url, headers=headers, json=draft_body)
                if res.status_code not in [200, 201]:
                    raise RuntimeError(f"Gmail draft creation failed: {res.text}")
                draft = res.json()
                draft_id = draft.get("id")
                msg_id = draft.get("message", {}).get("id")
                return ToolResult(
                    status="success",
                    data={
                        "action": "email_draft",
                        "draft_id": draft_id,
                        "message_id": msg_id,
                        "to": to,
                        "subject": subject
                    },
                    external_ids=[draft_id] if draft_id else [],
                    side_effect_state="CONFIRMED"
                )

            elif action in ["email_send", "send"]:
                to = params.get("to") or params.get("recipient", "")
                subject = params.get("subject", "Message from Relay")
                body = params.get("body") or params.get("content", "")

                raw_msg = self._create_message(to, subject, body)
                url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
                res = await client.post(url, headers=headers, json=raw_msg)
                if res.status_code not in [200, 201]:
                    raise RuntimeError(f"Gmail send failed: {res.text}")
                sent = res.json()
                message_id = sent.get("id")
                return ToolResult(
                    status="success",
                    data={
                        "action": "email_send",
                        "message_id": message_id,
                        "thread_id": sent.get("threadId"),
                        "to": to,
                        "subject": subject
                    },
                    external_ids=[message_id] if message_id else [],
                    side_effect_state="CONFIRMED"
                )

            else:
                raise ValueError(f"Unknown Gmail action: {action}")

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Union[ToolResult, Dict[str, Any]],
        ctx: ExecutionContext
    ) -> VerificationOutcome:
        message_id = result.get("message_id")
        credentials = ctx.credentials if ctx else None
        if not message_id or not credentials:
            return VerificationOutcome(
                result="failed",
                evidence={"error": "Missing message_id or credentials to verify email"},
                reason="Missing message_id or credentials"
            )

        cred_dict = json.loads(credentials) if isinstance(credentials, str) else credentials
        token = cred_dict.get("access_token") if isinstance(cred_dict, dict) else None
        if not token:
            return VerificationOutcome(
                result="failed",
                evidence={"error": "Missing access_token in credentials"},
                reason="Missing access token"
            )

        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                msg_data = res.json()
                evidence = {
                    "verified_message_id": message_id,
                    "thread_id": msg_data.get("threadId"),
                    "snippet": msg_data.get("snippet"),
                    "label_ids": msg_data.get("labelIds", [])
                }
                return VerificationOutcome(
                    result="passed",
                    evidence=evidence,
                    reason="Message confirmed via Gmail API"
                )
            return VerificationOutcome(
                result="failed",
                evidence={"http_status": res.status_code, "detail": res.text},
                reason=f"Gmail API returned HTTP {res.status_code}"
            )
