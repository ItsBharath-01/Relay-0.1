from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel
from app.models.entities import UserPreference
from app.security.crypto import hash_payload

from app.tools.registry.base import EffectClass, ActionSpec
from app.tools.registry import get_tool, get_tools_for_capability

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
    user approval preferences, action consequences, effect classes, and payload hashes.
    """

    def assess_action(
        self,
        capability_id: str,
        action: str,
        params: Dict[str, Any],
        preferences: Optional[UserPreference] = None,
        action_spec: Optional[ActionSpec] = None,
        tool_id: Optional[str] = None,
    ) -> RiskAssessment:
        prefs = preferences or UserPreference()
        p_hash = hash_payload(params)

        # 0. Resolve ActionSpec if not directly provided
        resolved_spec = action_spec
        if not resolved_spec:
            target_tool = get_tool(tool_id) if tool_id else None
            if not target_tool:
                candidate_tools = get_tools_for_capability(capability_id)
                if candidate_tools:
                    target_tool = candidate_tools[0]
            if target_tool:
                for spec in target_tool.describe_actions():
                    if spec.action == action or spec.capability_id == capability_id:
                        resolved_spec = spec
                        break

        # Rule 1: Financial or purchase actions (CRITICAL - ALWAYS REQUIRES APPROVAL, NO BYPASS)
        if any(w in action.lower() or w in str(params).lower() for w in ["pay", "purchase", "stripe", "checkout", "buy", "transfer", "refund"]):
            return RiskAssessment(
                risk_level="critical",
                requires_approval=True,  # Mandatory: cannot be disabled by user preference
                reason="Financial transaction, payment, or purchase execution detected.",
                target="Payment Gateway / Financial Account",
                consequences="Real funds will be transferred or charged to your account.",
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

        # Rule 3: Deletion or destructive wiping of data / calendar / emails / resources / IRREVERSIBLE
        is_deletion = any(w in capability_id.lower() or w in action.lower() for w in ["delete", "remove", "wipe", "drop", "destroy", "purge", "terminate"])
        if is_deletion or (resolved_spec and resolved_spec.effect_class == EffectClass.IRREVERSIBLE):
            req_app = True if prefs.ask_deleting is None else bool(prefs.ask_deleting)
            target = params.get("event_id") or params.get("id") or params.get("note_id") or ("all stored data" if any(w in action.lower() or w in capability_id.lower() for w in ["wipe", "purge"]) else "specified resource")
            is_critical = any(w in action.lower() or w in capability_id.lower() for w in ["wipe", "destroy", "purge", "drop"])
            level = "critical" if is_critical else "high"
            return RiskAssessment(
                risk_level=level,
                requires_approval=True if level == "critical" else req_app,
                reason="This action will permanently delete or wipe stored items or records." if is_deletion else "This action is irreversible and cannot be undone.",
                target=str(target),
                consequences="The item(s) will be permanently removed." if is_deletion else "System or external state will be permanently altered.",
                payload_hash=p_hash
            )

        # Rule 4: Browser automation actions
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

        # Rule 5: Scheduling calendar events with attendees
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

        # Rule 6: EffectClass evaluation when ActionSpec is present
        if resolved_spec:
            eff_class = resolved_spec.effect_class
            # Dynamic HTTP method check for api_request
            if capability_id == "api_request" or action in ("api_request", "request"):
                method = str(params.get("method", "GET")).upper()
                if method in ("GET", "HEAD", "OPTIONS"):
                    eff_class = EffectClass.READ_ONLY

            if eff_class == EffectClass.READ_ONLY:
                return RiskAssessment(
                    risk_level="low",
                    requires_approval=False,
                    reason="Read-only operation with no side-effects.",
                    target=None,
                    consequences="No destructive or consequential impact.",
                    payload_hash=p_hash
                )
            elif eff_class in (EffectClass.NON_IDEMPOTENT_WRITE, EffectClass.IDEMPOTENT_WRITE):
                # Non-idempotent writes default to requiring approval
                # Resource creation defaults to medium risk; other non-idempotent writes default to high risk
                is_create = any(w in action.lower() or w in capability_id.lower() for w in ["create", "draft", "make", "new", "insert", "add"])
                level = "medium" if is_create else ("high" if eff_class == EffectClass.NON_IDEMPOTENT_WRITE else "medium")
                return RiskAssessment(
                    risk_level=level,
                    requires_approval=True,
                    reason=f"Write operation '{action}' altering external state.",
                    target=resolved_spec.target_param or "Target resource",
                    consequences="External state will be modified.",
                    payload_hash=p_hash
                )

        # Rule 7: MCP tools without explicit read-only declarations default to write risk requiring approval
        is_mcp = (
            "mcp" in capability_id.lower()
            or "mcp" in action.lower()
            or (tool_id and "mcp" in tool_id.lower())
            or (not get_tools_for_capability(capability_id) and any(kw in action.lower() for kw in ["tool", "mcp"]))
        )
        if is_mcp:
            # Check if explicitly read-only via keywords
            if any(r in action.lower() or r in capability_id.lower() for r in ["read", "search", "get", "list", "fetch"]):
                return RiskAssessment(
                    risk_level="low",
                    requires_approval=False,
                    reason="Read-only MCP operation.",
                    target=None,
                    consequences="No side effects.",
                    payload_hash=p_hash
                )
            return RiskAssessment(
                risk_level="high",
                requires_approval=True,
                reason=f"MCP tool '{action}' lacks read-only declaration; defaulting to write approval.",
                target="MCP Server",
                consequences="Remote MCP service state may be modified.",
                payload_hash=p_hash
            )

        # Rule 8: Read-only or drafting actions (Safe defaults)
        is_write_keyword = any(w in action.lower() or w in capability_id.lower() for w in ["create", "update", "write", "post", "patch", "modify", "insert", "send"])
        if is_write_keyword:
            return RiskAssessment(
                risk_level="medium",
                requires_approval=False,
                reason=f"Write operation '{action}'.",
                target=None,
                consequences="Resource will be created or modified.",
                payload_hash=p_hash
            )

        return RiskAssessment(
            risk_level="low",
            requires_approval=False,
            reason="Read-only or local drafting operation with no external side-effects.",
            target=None,
            consequences="No destructive or consequential impact.",
            payload_hash=p_hash
        )

risk_classifier = RiskClassifier()

