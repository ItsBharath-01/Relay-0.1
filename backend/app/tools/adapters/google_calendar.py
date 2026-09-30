import json
from typing import Dict, Any, Optional, Tuple
import httpx

from app.tools.registry.base import BaseTool

class GoogleCalendarTool(BaseTool):
    id = "google_calendar"
    name = "Google Calendar"
    tool_type = "api"
    provides = ["calendar_read", "calendar_create", "calendar_delete"]
    requires_connection = "google_calendar"
    required_permissions = ["read", "create"]

    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        if not credentials:
            return False, "Google Calendar is not connected. Connect via OAuth in Connections."
        try:
            cred_dict = json.loads(credentials) if isinstance(credentials, str) else credentials
            token = cred_dict.get("access_token")
            if not token:
                return False, "Missing OAuth access token"

            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get("https://www.googleapis.com/calendar/v3/users/me/calendarList", headers=headers)
                if res.status_code == 200:
                    return True, "Google Calendar connected and healthy"
                elif res.status_code == 401:
                    return False, "Token expired or revoked. Reconnection needed."
                return False, f"Google Calendar API returned HTTP {res.status_code}"
        except Exception as e:
            return False, f"Connection check failed: {str(e)}"

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Dict[str, Any]:
        if not credentials:
            raise PermissionError("Google Calendar is not connected. User must connect Google Calendar in Connections first.")

        cred_dict = json.loads(credentials) if isinstance(credentials, str) else credentials
        token = cred_dict.get("access_token")
        if not token:
            raise PermissionError("Invalid or missing Google access token.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            if action in ["calendar_read", "read"]:
                url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                q_params = {"maxResults": 10, "singleEvents": True, "orderBy": "startTime"}
                res = await client.get(url, headers=headers, params=q_params)
                if res.status_code != 200:
                    raise RuntimeError(f"Google Calendar read failed: {res.text}")
                events = res.json().get("items", [])
                return {"action": "calendar_read", "count": len(events), "events": events}

            elif action in ["calendar_create", "create"]:
                summary = params.get("summary") or params.get("title", "Relay Scheduled Meeting")
                start_time = params.get("start_time")
                end_time = params.get("end_time")
                attendees = [{"email": e} for e in params.get("attendees", []) if isinstance(e, str)]
                description = params.get("description", "Scheduled by Relay Agent")

                event_body = {
                    "summary": summary,
                    "description": description,
                    "attendees": attendees,
                }
                if start_time:
                    event_body["start"] = {"dateTime": start_time}
                if end_time:
                    event_body["end"] = {"dateTime": end_time}

                url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                res = await client.post(url, headers=headers, json=event_body)
                if res.status_code not in [200, 201]:
                    raise RuntimeError(f"Google Calendar event creation failed: {res.text}")
                created = res.json()
                return {
                    "action": "calendar_create",
                    "event_id": created.get("id"),
                    "html_link": created.get("htmlLink"),
                    "summary": created.get("summary"),
                    "created": created.get("created"),
                    "status": created.get("status")
                }

            elif action in ["calendar_delete", "delete"]:
                event_id = params.get("event_id")
                if not event_id:
                    raise ValueError("event_id is required to delete calendar event.")
                url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}"
                res = await client.delete(url, headers=headers)
                if res.status_code not in [200, 204]:
                    raise RuntimeError(f"Google Calendar delete failed: {res.text}")
                return {"action": "calendar_delete", "event_id": event_id, "deleted": True}

            else:
                raise ValueError(f"Unknown Google Calendar action: {action}")

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        event_id = result.get("event_id")
        if not event_id or not credentials:
            return False, {"error": "Missing event_id or credentials to verify event"}

        cred_dict = json.loads(credentials) if isinstance(credentials, str) else credentials
        token = cred_dict.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        # Independently re-fetch from Google API to confirm real event exists
        url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                event_data = res.json()
                evidence = {
                    "verified_event_id": event_id,
                    "summary": event_data.get("summary"),
                    "status": event_data.get("status"),
                    "html_link": event_data.get("htmlLink"),
                    "attendees_count": len(event_data.get("attendees", []))
                }
                return True, evidence
            return False, {"http_status": res.status_code, "detail": res.text}
