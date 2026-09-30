from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel
from app.models.entities import UserPreference
from app.security.crypto import hash_payload

class RiskAssessment(BaseModel):
    risk_level: str  # "low" | "medium" | "high" | "critical"
    requires_approval: bool
    reason: str
    target: Optional[str] = None
    consequences: Optional[str] = None
    payload_hash: str

class RiskClassifier:
    """
    Deterministic rule-first risk classification engine that evaluates
    user approval preferences, action consequences, and payload hashes.
    """

    def assess_action(
        self,
        capability_id: str,
        action: str,
        params: Dict[str, Any],
        preferences: Optional[UserPreference] = None
    ) -> RiskAssessment:
        prefs = preferences or UserPreference()
        p_hash = hash_payload(params)

        # Rule 1: Deletion of data / calendar / emails
        if "delete" in capability_id or "delete" in action:
            req_app = True if prefs.ask_deleting is None else bool(prefs.ask_deleting)
            target = params.get("event_id") or params.get("id") or "specified resource"
            return RiskAssessment(
                risk_level="high",
                requires_approval=req_app,
                reason="This action will permanently delete an existing item or calendar appointment.",
                target=str(target),
                consequences="The item will be removed from your account.",
                payload_hash=p_hash
            )

        # Rule 2: Outgoing external communication (Email or Chat)
        if capability_id in ["email_send", "message_send"] or action in ["email_send", "send"]:
            recipient = params.get("to") or params.get("recipient") or params.get("channel") or "External Recipient"
            attendees = params.get("attendees", [])
            recipient_count = 1
            if isinstance(recipient, list):
                recipient_count = len(recipient)
            if attendees:
                recipient_count = max(recipient_count, len(attendees))

            # Threshold check
            threshold = prefs.threshold_people if prefs.threshold_people is not None else 5
            ask_msg = True if prefs.ask_external_messages is None else bool(prefs.ask_external_messages)
            exceeds_threshold = recipient_count >= threshold
            req_app = ask_msg or exceeds_threshold

            reason = f"Sending external message to '{recipient}'."
            if exceeds_threshold:
                reason += f" Affects {recipient_count} people (exceeds threshold of {threshold})."

            return RiskAssessment(
                risk_level="high",
                requires_approval=req_app,
                reason=reason,
                target=str(recipient),
                consequences="An actual message will be transmitted to external parties.",
                payload_hash=p_hash
            )

        # Rule 3: Scheduling calendar events with attendees
        if capability_id == "calendar_create" or action in ["calendar_create", "create"]:
            attendees = params.get("attendees", [])
            summary = params.get("summary") or params.get("title", "Meeting")
            ask_msg = True if prefs.ask_external_messages is None else bool(prefs.ask_external_messages)
            if attendees and ask_msg:
                return RiskAssessment(
                    risk_level="medium",
                    requires_approval=True,
                    reason=f"Creating calendar meeting '{summary}' inviting external attendees: {', '.join([str(a) for a in attendees])}.",
                    target=", ".join([str(a) for a in attendees]),
                    consequences="Google Calendar invites will be dispatched to attendees.",
                    payload_hash=p_hash
                )
            return RiskAssessment(
                risk_level="medium",
                requires_approval=False,
                reason=f"Creating internal calendar appointment '{summary}'.",
                target=summary,
                consequences="Event will be saved to your calendar.",
                payload_hash=p_hash
            )

        # Rule 4: Financial or purchase actions (CRITICAL - ALWAYS REQUIRES APPROVAL, NO BYPASS)
        if any(w in action.lower() or w in str(params).lower() for w in ["pay", "purchase", "stripe", "checkout", "buy", "transfer", "refund"]):
            return RiskAssessment(
                risk_level="critical",
                requires_approval=True,  # Mandatory: cannot be disabled by user preference
                reason="Financial transaction, payment, or purchase execution detected.",
                target="Payment Gateway / Financial Account",
                consequences="Real funds will be transferred or charged to your account.",
                payload_hash=p_hash
            )

        # Rule 5: Browser automation actions (P0-7 fix)
        if capability_id in ["browser_navigate", "browser_interact", "browser_click", "browser_fill"] or "browser" in action:
            url = params.get("url") or params.get("target") or "External website"
            is_form_submission = any(w in action.lower() or w in str(params).lower() for w in ["submit", "click", "type", "fill", "post", "login"])
            
            if is_form_submission:
                return RiskAssessment(
                    risk_level="high",
                    requires_approval=True,
                    reason=f"Automated browser will interact/submit data on '{url}'.",
                    target=str(url),
                    consequences="External website state may be altered or credentials submitted.",
                    payload_hash=p_hash
                )
            else:
                return RiskAssessment(
                    risk_level="medium",
                    requires_approval=False,
                    reason=f"Automated browser will navigate to external site '{url}'.",
                    target=str(url),
                    consequences="Page content will be downloaded and rendered by the headless browser.",
                    payload_hash=p_hash
                )

        # Rule 6: Read-only or drafting actions (Safe defaults)
        return RiskAssessment(
            risk_level="low",
            requires_approval=False,
            reason="Read-only or local drafting operation with no external side-effects.",
            target=None,
            consequences="No destructive or consequential impact.",
            payload_hash=p_hash
        )

risk_classifier = RiskClassifier()

