import asyncio
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.recovery import FailureDiagnosis, RecoveryPlan
from app.selection.engine import selection_engine
from app.tools.registry.capabilities import get_capability
from app.tools.registry import get_tool
from app.llm import get_llm_provider
from app.connections.resolver import redact_sensitive_data

class RecoveryEngine:
    """
    Deterministic first, LLM-reasoned second failure diagnosis and recovery engine.
    Validates all alternative tools and capabilities against backend registries and user permissions.
    """

    def classify_transient_error(self, error_msg: str) -> Optional[str]:
        """Identifies transient network or rate limit errors suitable for immediate backoff retry."""
        msg_lower = error_msg.lower()
        if any(w in msg_lower for w in ["timeout", "timed out", "connection reset", "temporarily unavailable"]):
            return "timeout"
        if any(w in msg_lower for w in ["rate limit", "429", "too many requests", "quota"]):
            return "rate_limit"
        if any(w in msg_lower for w in ["502", "503", "504", "bad gateway", "service unavailable"]):
            return "network"
        return None

    async def diagnose_failure(
        self,
        task_id: str,
        task_title: str,
        capability_id: str,
        problem: str,
        attempt: int = 1
    ) -> FailureDiagnosis:
        clean_problem = redact_sensitive_data(problem)
        
        # Check deterministic classification
        transient_type = self.classify_transient_error(str(clean_problem))
        if transient_type and attempt < 3:
            return FailureDiagnosis(
                failure_type=transient_type,
                cause=f"Transient {transient_type} error: {clean_problem}",
                recoverable=True,
                affected_task=task_title,
                recommended_strategy="retry_with_backoff"
            )

        if "reconnection" in str(clean_problem).lower() or "revoked" in str(clean_problem).lower():
            return FailureDiagnosis(
                failure_type="auth",
                cause=f"Authentication revoked or expired: {clean_problem}",
                recoverable=False,
                affected_task=task_title,
                recommended_strategy="reconnect_required"
            )

        # Fallback to structured LLM diagnosis
        prompt = (
            f"Task '{task_title}' (Capability: '{capability_id}') failed on attempt {attempt}.\n"
            f"Error/Observation: {clean_problem}\n\n"
            "Diagnose the failure type, root cause, whether it is recoverable, and recommend strategy."
        )
        try:
            provider = get_llm_provider()
            diag, _ = await provider.generate_structured(
                schema=FailureDiagnosis,
                prompt=prompt,
                system_prompt="You are Relay's Failure Diagnostic Agent. Diagnose the failure objectively.",
                temperature=0.1
            )
            return diag
        except Exception:
            return FailureDiagnosis(
                failure_type="verification_failed" if "verification" in str(clean_problem).lower() else "unknown",
                cause=str(clean_problem),
                recoverable=True,
                affected_task=task_title,
                recommended_strategy="alternative_tool"
            )

    async def build_recovery_plan(
        self,
        user_id: str,
        task_id: str,
        capability_id: str,
        current_action: str,
        current_params: Dict[str, Any],
        failed_tool_id: str,
        diagnosis: FailureDiagnosis,
        db: AsyncSession,
        excluded_tool_ids: Optional[List[str]] = None
    ) -> Optional[RecoveryPlan]:
        excluded = list(excluded_tool_ids or [])
        if failed_tool_id not in excluded:
            excluded.append(failed_tool_id)

        if diagnosis.recommended_strategy == "retry_with_backoff":
            return RecoveryPlan(
                strategy="retry_with_backoff",
                alternative_capability=capability_id,
                alternative_tool=failed_tool_id,
                updated_action=current_action,
                updated_params=current_params,
                reason=f"Retrying after transient error ({diagnosis.cause})",
                expected_result="Task execution succeeds on retry"
            )

        # Find alternative tool for this capability
        decision = await selection_engine.evaluate_candidates(
            user_id=user_id,
            capability_id=capability_id,
            db=db,
            task_id=task_id,
            excluded_tool_ids=excluded
        )

        if decision.selected_tool_id:
            alt_tool = get_tool(decision.selected_tool_id)
            return RecoveryPlan(
                strategy="alternative_tool",
                alternative_capability=capability_id,
                alternative_tool=alt_tool.id,
                updated_action=current_action,
                updated_params=current_params,
                reason=f"Recovering using alternative authorized tool '{alt_tool.name}'. {decision.explanation}",
                expected_result=f"Complete '{capability_id}' via {alt_tool.name}"
            )

        return None

    def validate_plan(self, plan: RecoveryPlan, allowed_capabilities: List[str]) -> bool:
        """Validates that a proposed recovery plan references valid registry capabilities and allowed strategies."""
        allowed_strategies = ["retry_with_backoff", "alternative_tool", "alternative_params", "replan_remaining", "abort"]
        if plan.strategy not in allowed_strategies:
            return False

        if plan.alternative_capability and plan.alternative_capability not in allowed_capabilities:
            return False

        if plan.alternative_tool:
            tool = get_tool(plan.alternative_tool)
            if not tool:
                return False

        return True

recovery_engine = RecoveryEngine()
