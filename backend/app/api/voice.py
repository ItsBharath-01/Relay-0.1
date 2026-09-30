"""
voice.py — P2-1 LLM-based voice intent classification endpoint.

Architecture:
    React → POST /api/voice/process → this module
           → get_llm_provider().generate_structured(VoiceIntent, ...)
           → OllamaProvider → qwen3:4b
           → response routed by confidence threshold

Security invariants:
  - Transcript is untrusted external data; it never becomes a system instruction.
  - Approval / rejection actions still go through decide_approval() with full ownership checks.
  - No credentials, tokens, or private data are exposed to the LLM.
  - LLM output is validated against the VoiceIntent Pydantic schema before any action is taken.
"""

from typing import Optional, Dict, Any, List, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
import logging

from app.core.database import get_db
from app.models.entities import Execution, Plan, Task, Approval, Recovery, User
from app.security.auth import get_current_user
from app.llm import get_llm_provider
from app.llm.errors import ProviderNotConfiguredError, ProviderNotImplementedError
from app.api.approvals import decide_approval, ApprovalDecisionRequest
from app.agent.prompts.voice_intent import build_voice_intent_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice"])

# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

VALID_INTENT_TYPES = Literal[
    "create_goal",
    "modify_goal",
    "pause_execution",
    "resume_execution",
    "cancel_execution",
    "approve",
    "reject",
    "ask_status",
    "ask_explanation",
    "ask_clarification",
    "unknown",
]


class VoiceIntent(BaseModel):
    """Pydantic schema validated against every LLM response for voice commands."""
    intent_type: VALID_INTENT_TYPES
    goal: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    entities: Dict[str, Any] = Field(default_factory=dict)
    requested_action: str
    language: str = "en"
    clarification_needed: bool = False
    clarification_question: Optional[str] = None

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str) -> str:
        supported = {"en", "hi", "kn", "ta", "te", "ml", "bn"}
        lang = v.lower().strip()[:2]
        return lang if lang in supported else "en"


class VoiceCommandRequest(BaseModel):
    transcript: str
    language: str = "en"
    execution_id: Optional[str] = None


class VoiceCommandResponse(BaseModel):
    transcript: str
    intent: str
    reply_text: str
    action_taken: Optional[str] = None
    execution_id: Optional[str] = None
    confidence: float = 0.0
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    llm_used: bool = True


# ──────────────────────────────────────────────────────────────────────────────
# Confidence thresholds
# ──────────────────────────────────────────────────────────────────────────────

CONFIDENCE_HIGH = 0.75    # act directly
CONFIDENCE_MEDIUM = 0.50  # confirm before acting

# ──────────────────────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/process", response_model=VoiceCommandResponse)
async def process_voice_command(
    req: VoiceCommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Classify a spoken voice command via LLM intent classification and act on it.

    The transcript is treated as untrusted external data at all times.
    Actions that affect execution state or approvals are executed server-side
    with full ownership and permission checks.
    """
    transcript = req.transcript.strip()
    if not transcript:
        return VoiceCommandResponse(
            transcript="",
            intent="unknown",
            reply_text="I could not hear anything. Please try speaking again.",
            confidence=0.0,
            llm_used=False,
        )

    # ── 1. Fetch execution context ──────────────────────────────────────────
    execution = await _fetch_execution(req.execution_id, current_user.id, db)
    exec_context = _build_exec_context(execution)

    # ── 2. LLM-based intent classification ─────────────────────────────────
    voice_intent, llm_used = await _classify_intent_with_llm(
        transcript=transcript,
        exec_context=exec_context,
        language=req.language,
    )

    # ── 3. Route by confidence threshold ───────────────────────────────────
    if voice_intent.confidence < CONFIDENCE_MEDIUM:
        # Low confidence — ask user to rephrase
        reply = (
            voice_intent.clarification_question
            or "I'm not sure I understood. Could you please rephrase?"
        )
        return VoiceCommandResponse(
            transcript=transcript,
            intent=voice_intent.intent_type,
            reply_text=reply,
            execution_id=execution.id if execution else None,
            confidence=voice_intent.confidence,
            clarification_needed=True,
            clarification_question=reply,
            llm_used=llm_used,
        )

    if CONFIDENCE_MEDIUM <= voice_intent.confidence < CONFIDENCE_HIGH:
        # Medium confidence — request explicit confirmation from frontend
        q = (
            voice_intent.clarification_question
            or f"Did you mean to {voice_intent.requested_action}? Please confirm."
        )
        return VoiceCommandResponse(
            transcript=transcript,
            intent=voice_intent.intent_type,
            reply_text=q,
            execution_id=execution.id if execution else None,
            confidence=voice_intent.confidence,
            clarification_needed=True,
            clarification_question=q,
            llm_used=llm_used,
        )

    # High confidence — act
    reply, action_taken = await _execute_intent(
        voice_intent=voice_intent,
        execution=execution,
        current_user=current_user,
        db=db,
    )

    return VoiceCommandResponse(
        transcript=transcript,
        intent=voice_intent.intent_type,
        reply_text=reply,
        action_taken=action_taken,
        execution_id=execution.id if execution else None,
        confidence=voice_intent.confidence,
        clarification_needed=False,
        llm_used=llm_used,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _fetch_execution(
    execution_id: Optional[str],
    user_id: str,
    db: AsyncSession,
) -> Optional[Execution]:
    """Fetch execution with all relations loaded, scoped to the authenticated user."""
    load_opts = [
        selectinload(Execution.plan).selectinload(Plan.tasks),
        selectinload(Execution.goal),
        selectinload(Execution.approvals),
        selectinload(Execution.recoveries),
        selectinload(Execution.events),
    ]

    if execution_id:
        stmt = (
            select(Execution)
            .options(*load_opts)
            .where(Execution.id == execution_id, Execution.user_id == user_id)
        )
        res = await db.execute(stmt)
        execution = res.scalar_one_or_none()
        if execution:
            return execution

    # Fall back to most recent execution for this user
    stmt = (
        select(Execution)
        .options(*load_opts)
        .where(Execution.user_id == user_id)
        .order_by(Execution.started_at.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


def _build_exec_context(execution: Optional[Execution]) -> str:
    """Build a brief, backend-verified execution summary for the LLM prompt."""
    if not execution:
        return "No active execution."

    pending_approvals = [
        a for a in (execution.approvals or []) if a.status == "pending"
    ]
    recent_recovery = (execution.recoveries or [])[-1] if execution.recoveries else None

    lines = [
        f"Execution ID: {execution.id}",
        f"Goal: {execution.goal.text if execution.goal else 'N/A'}",
        f"Status: {execution.status}",
        f"Progress: {int(execution.progress * 100)}%",
        f"Current Action: {execution.current_action or 'None'}",
        f"Pending Approvals: {len(pending_approvals)}",
    ]
    if pending_approvals:
        pa = pending_approvals[0]
        lines.append(f"Pending Approval Action: {pa.action} (risk={pa.risk})")
    if recent_recovery:
        lines.append(
            f"Last Recovery: {recent_recovery.original_tool_id} → {recent_recovery.alternative_tool_id}"
        )
    return "\n".join(lines)


async def _classify_intent_with_llm(
    transcript: str,
    exec_context: str,
    language: str,
) -> tuple[VoiceIntent, bool]:
    """
    Call the configured LLM provider to classify voice intent.

    Falls back to a safe UNKNOWN intent if the LLM is unavailable — this is
    the only scenario where the LLM is not used. No keyword-matching fallback.

    Returns:
        (VoiceIntent, llm_was_used: bool)
    """
    system_prompt, user_prompt = build_voice_intent_prompt(
        transcript=transcript,
        exec_context=exec_context,
        language=language,
    )

    try:
        provider = get_llm_provider()
        intent_obj, _meta = await provider.generate_structured(
            schema=VoiceIntent,
            prompt=user_prompt,
            system_prompt=system_prompt,
            language=language,
            max_retries=2,
            temperature=0.0,
            prompt_version="voice_intent_v1.0",
        )
        logger.info(
            "Voice intent classified",
            extra={
                "intent_type": intent_obj.intent_type,
                "confidence": intent_obj.confidence,
                "language": intent_obj.language,
            },
        )
        return intent_obj, True

    except (ProviderNotConfiguredError, ProviderNotImplementedError) as exc:
        logger.warning("LLM provider unavailable for voice intent: %s", exc)
        return VoiceIntent(
            intent_type="unknown",
            confidence=0.0,
            requested_action="llm_unavailable",
            clarification_needed=True,
            clarification_question="The AI assistant is currently unavailable. Please try again later.",
        ), False

    except Exception as exc:
        logger.error("Voice intent LLM call failed: %s", exc, exc_info=True)
        return VoiceIntent(
            intent_type="unknown",
            confidence=0.0,
            requested_action="llm_error",
            clarification_needed=True,
            clarification_question="I encountered an error processing your command. Please try again.",
        ), False


async def _execute_intent(
    voice_intent: VoiceIntent,
    execution: Optional[Execution],
    current_user: User,
    db: AsyncSession,
) -> tuple[str, Optional[str]]:
    """
    Execute a high-confidence intent. Returns (reply_text, action_taken).

    All state mutations go through the database with ownership enforcement.
    Approval decisions go through decide_approval() which has its own
    ownership, status, and payload-hash checks.
    """
    intent = voice_intent.intent_type
    action_taken: Optional[str] = None

    # ── Status ──
    if intent == "ask_status":
        if execution:
            reply = (
                f"Current status is {execution.status}, "
                f"progress is {int(execution.progress * 100)} percent. "
                f"{execution.current_action or ''}."
            )
        else:
            reply = "You have no active tasks running right now."

    # ── Pause ──
    elif intent == "pause_execution":
        if execution and execution.status == "running":
            execution.status = "paused"
            await db.commit()
            action_taken = "paused"
            reply = "Execution has been paused before the next tool call."
        else:
            reply = "No running execution to pause."

    # ── Resume ──
    elif intent == "resume_execution":
        if execution and execution.status == "paused":
            execution.status = "running"
            await db.commit()
            action_taken = "resumed"
            reply = "Execution resumed."
        else:
            reply = "Execution is not currently paused."

    # ── Cancel ──
    elif intent == "cancel_execution":
        if execution and execution.status in {"running", "paused", "waiting_approval"}:
            execution.status = "cancelled"
            await db.commit()
            action_taken = "cancelled"
            reply = "Execution has been cancelled."
        else:
            reply = "No active execution to cancel."

    # ── Approve ──
    elif intent == "approve":
        if execution:
            pending = next(
                (a for a in execution.approvals if a.status == "pending"), None
            )
            if pending:
                await decide_approval(
                    approval_id=pending.id,
                    req=ApprovalDecisionRequest(decision="approved", decided_by="voice"),
                    current_user=current_user,
                    db=db,
                )
                action_taken = "approved"
                reply = f"Approved action '{pending.action}'. Resuming execution."
            else:
                reply = "There are no pending actions requiring your approval right now."
        else:
            reply = "No pending approval found."

    # ── Reject ──
    elif intent == "reject":
        if execution:
            pending = next(
                (a for a in execution.approvals if a.status == "pending"), None
            )
            if pending:
                await decide_approval(
                    approval_id=pending.id,
                    req=ApprovalDecisionRequest(decision="rejected", decided_by="voice"),
                    current_user=current_user,
                    db=db,
                )
                action_taken = "rejected"
                reply = f"Rejected action '{pending.action}'. The task has been stopped."
            else:
                reply = "There are no pending actions requiring your approval."
        else:
            reply = "No pending approval found."

    # ── Explanation ──
    elif intent == "ask_explanation":
        if execution and execution.events:
            tool_ev = next(
                (e for e in reversed(execution.events) if e.type == "tool_selected"),
                None,
            )
            rec = (execution.recoveries or [])[-1] if execution.recoveries else None
            if tool_ev:
                reply = tool_ev.message
            elif rec:
                reply = (
                    f"The original tool {rec.original_tool_id} encountered an issue: "
                    f"{rec.problem}. Relay recovered using {rec.alternative_tool_id}."
                )
            else:
                reply = "No tool decision or recovery information is available yet."
        else:
            reply = "No active execution information found."

    # ── Clarification ──
    elif intent == "ask_clarification":
        reply = (
            voice_intent.clarification_question
            or "Could you please be more specific about what you'd like to know?"
        )

    # ── Create goal ──
    elif intent == "create_goal":
        extracted = voice_intent.goal or voice_intent.requested_action
        reply = (
            f"I understood your goal: '{extracted}'. "
            "You can submit this as a new goal from the main interface."
        )

    # ── Modify goal ──
    elif intent == "modify_goal":
        reply = (
            "Goal modification via voice is not yet implemented. "
            "Please edit your goal from the main interface."
        )

    # ── Unknown / fallback ──
    else:
        reply = (
            voice_intent.clarification_question
            or "I'm not sure what you meant. Could you please rephrase your command?"
        )

    return reply, action_taken
