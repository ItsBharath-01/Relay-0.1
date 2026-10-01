import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker
from app.models.entities import (
    Execution,
    Plan,
    Task,
    Goal,
    User,
    UserPreference,
    Approval,
    Recovery,
    Verification,
    Connection,
)
from app.selection.engine import selection_engine
from app.risk.classifier import risk_classifier
from app.tools.registry import get_tool
from app.events.manager import event_broadcaster
from app.connections.resolver import connection_resolver, redact_sensitive_data, ConnectionRevokedError
from app.verification.engine import verification_engine
from app.recovery.engine import recovery_engine


class ExecutionRunner:
    """
    Durable state machine executing real tools, real verification,
    real approval gating, and real recovery.
    """

    async def start_execution_background(self, execution_id: str):
        """Launches the execution state machine in an asynchronous background task."""
        asyncio.create_task(self.run_execution(execution_id))

    async def run_execution(self, execution_id: str):
        async with async_session_maker() as db:
            # Load execution with plan and tasks
            stmt = (
                select(Execution)
                .options(
                    selectinload(Execution.plan).selectinload(Plan.tasks),
                    selectinload(Execution.goal),
                    selectinload(Execution.user).selectinload(User.preferences)
                )
                .where(Execution.id == execution_id)
            )
            res = await db.execute(stmt)
            execution = res.scalar_one_or_none()
            if not execution:
                return

            plan = execution.plan
            goal = execution.goal
            user = execution.user
            preferences = user.preferences or UserPreference(user_id=user.id)
            tasks = sorted(plan.tasks, key=lambda t: t.order)
            total_tasks = len(tasks)

            await event_broadcaster.emit(
                db, execution_id, "task_started",
                f"Execution started for goal: '{goal.text}'",
                payload={"goal": goal.text, "total_tasks": total_tasks}
            )

            completed_count = 0
            tools_used = set()
            recoveries_count = 0
            approvals_count = 0

            for current_idx, task in enumerate(tasks):
                # 1. Check Pause / Cancel between steps
                await db.refresh(execution)
                while execution.status == "paused":
                    await event_broadcaster.emit(
                        db, execution_id, "execution_paused",
                        f"Execution paused before Task {task.order}: '{task.title}'",
                        task_id=task.id
                    )
                    # Poll until resumed or cancelled
                    await asyncio.sleep(2.0)
                    await db.refresh(execution)

                if execution.status == "cancelled":
                    await event_broadcaster.emit(
                        db, execution_id, "execution_cancelled",
                        "Execution was cancelled by user.",
                        task_id=task.id
                    )
                    execution.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    return

                # --- P0-2 FIX: enforce depends_on before running this task ---
                dep_ids: list = task.depends_on or []
                if dep_ids:
                    max_wait = 300  # seconds
                    waited = 0
                    while waited < max_wait:
                        await db.refresh(task)
                        dep_tasks = [t for t in tasks if t.id in dep_ids]
                        failed_deps = [t for t in dep_tasks if t.status == "failed"]
                        if failed_deps:
                            task.status = "failed"
                            completed_count = len([t for t in tasks if t.status == "completed"])
                            execution.outcome = "PARTIALLY_COMPLETED" if completed_count > 0 else "BLOCKED"
                            execution.evidence_level = "ACTION_EXECUTED" if completed_count > 0 else "ACTION_REQUESTED"
                            execution.status = "failed"
                            execution.completed_at = datetime.now(timezone.utc)
                            execution.outcome_summary = f"Task '{task.title}' skipped: dependency '{failed_deps[0].title}' failed."
                            await db.commit()
                            await event_broadcaster.emit(
                                db, execution_id, "task_failed",
                                f"Task '{task.title}' skipped: dependency '{failed_deps[0].title}' failed.",
                                task_id=task.id,
                            )
                            await event_broadcaster.emit(
                                db, execution_id, "execution_failed",
                                f"Execution stopped: prerequisite task failed.",
                                task_id=task.id,
                                payload={
                                    "outcome": execution.outcome,
                                    "evidence_level": execution.evidence_level,
                                    "summary": execution.outcome_summary
                                }
                            )
                            return
                        all_done = all(t.status == "completed" for t in dep_tasks)
                        if all_done:
                            break
                        await asyncio.sleep(1.0)
                        waited += 1
                    else:
                        # Timeout waiting for deps
                        task.status = "failed"
                        completed_count = len([t for t in tasks if t.status == "completed"])
                        execution.outcome = "PARTIALLY_COMPLETED" if completed_count > 0 else "FAILED"
                        execution.evidence_level = "ACTION_EXECUTED" if completed_count > 0 else "ACTION_REQUESTED"
                        execution.status = "failed"
                        execution.completed_at = datetime.now(timezone.utc)
                        execution.outcome_summary = f"Task '{task.title}' timed out waiting for dependencies."
                        await db.commit()
                        await event_broadcaster.emit(
                            db, execution_id, "task_failed",
                            f"Task '{task.title}' timed out waiting for dependencies.",
                            task_id=task.id,
                        )
                        await event_broadcaster.emit(
                            db, execution_id, "execution_failed",
                            f"Execution stopped: dependency wait timed out.",
                            task_id=task.id,
                            payload={
                                "outcome": execution.outcome,
                                "evidence_level": execution.evidence_level,
                                "summary": execution.outcome_summary
                            }
                        )
                        return

                # Mark task running
                task.status = "running"
                execution.current_task_id = task.id
                execution.current_action = task.title
                await db.commit()

                await event_broadcaster.emit(
                    db, execution_id, "progress_updated",
                    f"Starting Task {task.order} of {total_tasks}: {task.title}",
                    task_id=task.id,
                    payload={"order": task.order, "total": total_tasks, "progress": completed_count / total_tasks}
                )

                # 2. Tool Selection Engine
                decision = await selection_engine.evaluate_candidates(
                    user_id=user.id,
                    capability_id=task.capability_id,
                    db=db,
                    task_id=task.id
                )

                await event_broadcaster.emit(
                    db, execution_id, "tool_discovery",
                    f"Discovered {len(decision.candidate_checks)} candidate tools for capability '{task.capability_id}'.",
                    task_id=task.id,
                    payload={"candidates": [c.model_dump() for c in decision.candidate_checks]}
                )

                if not decision.selected_tool_id:
                    # Honest failure: missing connection / capability
                    task.status = "failed"
                    completed_count = len([t for t in tasks if t.status == "completed"])
                    execution.outcome = "PARTIALLY_COMPLETED" if completed_count > 0 else "BLOCKED"
                    execution.evidence_level = "ACTION_EXECUTED" if completed_count > 0 else "ACTION_REQUESTED"
                    execution.status = "failed"
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.outcome_summary = (
                        f"I can understand this goal, but no authorized tool currently provides the capability '{task.capability_id}'."
                    )
                    await db.commit()

                    fail_msg = f"I can understand this goal, but no authorized tool currently provides the capability '{task.capability_id}'."
                    await event_broadcaster.emit(
                        db, execution_id, "task_failed",
                        fail_msg,
                        task_id=task.id,
                        payload={
                            "capability": task.capability_id,
                            "explanation": decision.explanation,
                            "candidate_checks": [c.model_dump() for c in decision.candidate_checks],
                            "guidance": "Connect or authorize an application providing this capability in Connections to proceed."
                        }
                    )
                    await event_broadcaster.emit(
                        db, execution_id, "execution_failed",
                        f"Execution stopped: required capability '{task.capability_id}' is not available.",
                        task_id=task.id,
                        payload={
                            "outcome": execution.outcome,
                            "evidence_level": execution.evidence_level,
                            "summary": execution.outcome_summary
                        }
                    )
                    return

                selected_tool = get_tool(decision.selected_tool_id)
                task.selected_tool_id = selected_tool.id
                tools_used.add(selected_tool.name)
                await db.commit()

                await event_broadcaster.emit(
                    db, execution_id, "tool_selected",
                    f"Selected tool: {selected_tool.name}. {decision.explanation}",
                    task_id=task.id,
                    tool_id=selected_tool.id,
                    payload={"decision": decision.model_dump()}
                )

                # 3. Retrieve Credentials if needed via ConnectionResolver (P1-2)
                raw_credentials = None
                if selected_tool.requires_connection:
                    try:
                        raw_credentials = await connection_resolver.resolve_connection(
                            user_id=user.id,
                            app_id=selected_tool.requires_connection,
                            required_permissions=selected_tool.required_permissions,
                            db=db
                        )
                    except ConnectionRevokedError as cre:
                        task.status = "failed"
                        execution.status = "failed"
                        execution.completed_at = datetime.now(timezone.utc)
                        await db.commit()
                        await event_broadcaster.emit(
                            db, execution_id, "task_failed",
                            f"Connection revoked or expired for '{selected_tool.requires_connection}'. Reconnect in Connections.",
                            task_id=task.id,
                            payload={"error": str(cre), "reconnect_required": True}
                        )
                        return
                    except Exception as ce:
                        task.status = "failed"
                        execution.status = "failed"
                        execution.completed_at = datetime.now(timezone.utc)
                        await db.commit()
                        await event_broadcaster.emit(
                            db, execution_id, "task_failed",
                            f"Credential resolution error: {str(ce)}",
                            task_id=task.id,
                            payload={"error": str(ce)}
                        )
                        return

                # --- P0-1 FIX: read action and params from DB (set by planner) ---
                action_name = task.action or task.capability_id
                # Start with the LLM-generated params; fall back to empty dict
                action_params: Dict[str, Any] = dict(task.params) if task.params else {}


                # Resolve @task:<id> and source_task_id references
                source_task_id = action_params.pop("source_task_id", None)
                if source_task_id:
                    ref_task = next((t for t in tasks if t.id == source_task_id), None)
                    if ref_task and ref_task.result and isinstance(ref_task.result, dict):
                        ref_result = ref_task.result
                        if "content" in ref_result and "text" not in action_params:
                            action_params["text"] = str(ref_result["content"])
                        if "results" in ref_result and "text" not in action_params:
                            snippets = [
                                f"{r.get('title','')}: {r.get('snippet','')}"
                                for r in ref_result["results"]
                                if r.get("title") or r.get("snippet")
                            ]
                            action_params["text"] = "\n\n".join(snippets)

                # Scan all param keys for @task:<id> references
                for p_key, p_val in list(action_params.items()):
                    if isinstance(p_val, str) and p_val.startswith("@task:"):
                        ref_id = p_val.split("@task:", 1)[1].strip()
                        ref_task = next((t for t in tasks if t.id == ref_id or str(t.order) == ref_id), None)
                        if ref_task and ref_task.result:
                            if isinstance(ref_task.result, dict):
                                action_params[p_key] = ref_task.result.get("content") or ref_task.result.get("summary") or json.dumps(ref_task.result)
                            else:
                                action_params[p_key] = str(ref_task.result)


                # Fallback: if text/content still missing, aggregate completed prior tasks' output
                if not action_params.get("text") and not action_params.get("content"):
                    prior_parts = []
                    for prev_t in tasks:
                        if prev_t.id == task.id:
                            break
                        if prev_t.status == "completed" and prev_t.result and isinstance(prev_t.result, dict):
                            if "results" in prev_t.result:
                                prior_parts.extend(
                                    f"{r.get('title','')}: {r.get('snippet','')}"
                                    for r in prev_t.result["results"]
                                    if r.get("title") or r.get("snippet")
                                )
                            elif "content" in prev_t.result:
                                prior_parts.append(str(prev_t.result["content"]))
                    if prior_parts:
                        action_params["text"] = "\n\n".join(prior_parts)

                # Always ensure a fallback query param for web_search if planner omitted it
                if action_name == "web_search" and not action_params.get("query"):
                    action_params["query"] = goal.text

                # 4. Risk Classifier & Approval Gate
                risk_assessment = risk_classifier.assess_action(
                    capability_id=task.capability_id,
                    action=action_name,
                    params=action_params,
                    preferences=preferences
                )

                await event_broadcaster.emit(
                    db, execution_id, "risk_classified",
                    f"Risk level: {risk_assessment.risk_level.upper()}. {risk_assessment.reason}",
                    task_id=task.id,
                    tool_id=selected_tool.id,
                    payload=risk_assessment.model_dump()
                )

                if risk_assessment.requires_approval:
                    approvals_count += 1
                    # Server-side Approval Gate
                    approval = Approval(
                        execution_id=execution_id,
                        task_id=task.id,
                        action=action_name,
                        target=risk_assessment.target,
                        content=action_params,
                        payload_hash=risk_assessment.payload_hash,
                        reason=risk_assessment.reason,
                        risk=risk_assessment.risk_level,
                        consequences=risk_assessment.consequences,
                        status="pending"
                    )
                    db.add(approval)
                    execution.status = "waiting_approval"
                    task.status = "waiting_approval"
                    await db.commit()

                    await event_broadcaster.emit(
                        db, execution_id, "approval_required",
                        f"Approval required: {risk_assessment.reason}",
                        task_id=task.id,
                        tool_id=selected_tool.id,
                        payload={
                            "approval_id": approval.id,
                            "action": action_name,
                            "target": risk_assessment.target,
                            "risk": risk_assessment.risk_level,
                            "content": action_params,
                            "reason": risk_assessment.reason
                        }
                    )

                    # Block execution until approval decision is made
                    approved = False
                    while True:
                        await asyncio.sleep(2.0)
                        await db.refresh(approval)
                        if approval.status == "approved":
                            approved = True
                            break
                        elif approval.status in ["rejected", "expired"]:
                            approved = False
                            break
                        
                        # Also check if execution was cancelled while waiting
                        await db.refresh(execution)
                        if execution.status == "cancelled":
                            return

                    if not approved:
                        task.status = "rejected"
                        execution.status = "stopped"
                        execution.completed_at = datetime.now(timezone.utc)
                        await db.commit()

                        await event_broadcaster.emit(
                            db, execution_id, "approval_received",
                            "Action rejected by user. Execution stopped.",
                            task_id=task.id,
                            payload={"approval_id": approval.id, "decision": "rejected"}
                        )
                        return

                    # Approval granted
                    execution.status = "running"
                    task.status = "running"
                    await db.commit()

                    await event_broadcaster.emit(
                        db, execution_id, "approval_received",
                        f"Action approved by {approval.decided_by or 'user'}. Continuing execution.",
                        task_id=task.id,
                        payload={"approval_id": approval.id, "decision": "approved"}
                    )

                # 5. Execute Action
                await event_broadcaster.emit(
                    db, execution_id, "action_started",
                    f"Executing '{action_name}' via {selected_tool.name}...",
                    task_id=task.id,
                    tool_id=selected_tool.id
                )

                tool_result = None
                tool_error = None

                try:
                    tool_result = await selected_tool.execute(
                        action=action_name,
                        params=action_params,
                        credentials=raw_credentials
                    )
                    task.result = tool_result
                    await db.commit()

                    await event_broadcaster.emit(
                        db, execution_id, "observation",
                        f"Received real response from {selected_tool.name}.",
                        task_id=task.id,
                        tool_id=selected_tool.id,
                        payload=tool_result
                    )
                except Exception as e:
                    tool_error = str(e)
                    task.error = {"message": tool_error}
                    await db.commit()

                # 6. Goal- and Tool-Aware Verification (P1-7)
                verified = False
                verification_evidence = {}

                if tool_result and not tool_error:
                    await event_broadcaster.emit(
                        db, execution_id, "verification_started",
                        f"Independently verifying outcome of '{action_name}' via {selected_tool.name}...",
                        task_id=task.id,
                        tool_id=selected_tool.id
                    )

                    try:
                        v_res = await verification_engine.verify_task_outcome(
                            capability_id=task.capability_id,
                            action=action_name,
                            params=action_params,
                            result=tool_result,
                            credentials=raw_credentials,
                            tool_id=selected_tool.id
                        )
                        verified = (v_res.result == "passed")
                        verification_evidence = v_res.evidence
                    except Exception as ve:
                        verified = False
                        verification_evidence = {"error": str(ve)}

                    v_entity = Verification(
                        execution_id=execution_id,
                        task_id=task.id,
                        criterion=f"Verify {action_name} outcome",
                        result="passed" if verified else "failed",
                        evidence=verification_evidence
                    )
                    db.add(v_entity)
                    await db.commit()

                    await event_broadcaster.emit(
                        db, execution_id, "verification_completed",
                        "Verification passed with real evidence." if verified else "Verification failed: state check did not match expected outcome.",
                        task_id=task.id,
                        tool_id=selected_tool.id,
                        payload={
                            "result": "passed" if verified else "failed",
                            "criterion": v_entity.criterion,
                            "evidence": redact_sensitive_data(verification_evidence)
                        }
                    )

                # 7. Real Failure Diagnosis & Recovery (P1-1 & P1-2)
                if tool_error or not verified:
                    recoveries_count += 1
                    problem_desc = tool_error or "Verification check failed against real system state"

                    await event_broadcaster.emit(
                        db, execution_id, "task_failed",
                        f"Task failed: {redact_sensitive_data(problem_desc)}",
                        task_id=task.id,
                        tool_id=selected_tool.id,
                        payload={"error": redact_sensitive_data(problem_desc)}
                    )

                    # Diagnose failure
                    diagnosis = await recovery_engine.diagnose_failure(
                        task_id=task.id,
                        task_title=task.title,
                        capability_id=task.capability_id,
                        problem=problem_desc,
                        attempt=1
                    )

                    await event_broadcaster.emit(
                        db, execution_id, "diagnosis_stage",
                        f"Diagnosed failure ({diagnosis.failure_type}): {diagnosis.cause}. Recommended: {diagnosis.recommended_strategy}.",
                        task_id=task.id,
                        payload=diagnosis.model_dump()
                    )

                    # Build recovery plan
                    recovery_plan = await recovery_engine.build_recovery_plan(
                        user_id=user.id,
                        task_id=task.id,
                        capability_id=task.capability_id,
                        current_action=action_name,
                        current_params=action_params,
                        failed_tool_id=selected_tool.id,
                        diagnosis=diagnosis,
                        db=db,
                        excluded_tool_ids=[selected_tool.id]
                    )

                    if recovery_plan and recovery_plan.alternative_tool:
                        alt_tool = get_tool(recovery_plan.alternative_tool)
                        if alt_tool:
                            recovery = Recovery(
                                execution_id=execution_id,
                                task_id=task.id,
                                original_tool_id=selected_tool.id,
                                problem=problem_desc,
                                alternative_tool_id=alt_tool.id,
                                reason=recovery_plan.reason,
                                status="pending"
                            )
                            db.add(recovery)
                            await db.commit()

                            await event_broadcaster.emit(
                                db, execution_id, "recovery_started",
                                f"Attempting recovery via {alt_tool.name}...",
                                task_id=task.id,
                                tool_id=alt_tool.id,
                                payload={
                                    "original_tool_id": selected_tool.id,
                                    "alternative_tool_id": alt_tool.id,
                                    "original_tool": selected_tool.name,
                                    "alternative_tool": alt_tool.name,
                                    "strategy": recovery_plan.strategy,
                                    "reason": recovery_plan.reason
                                }
                            )

                            # Resolve credentials for alternative tool via ConnectionResolver (P1-2)
                            alt_creds = None
                            if alt_tool.requires_connection:
                                try:
                                    alt_creds = await connection_resolver.resolve_connection(
                                        user_id=user.id,
                                        app_id=alt_tool.requires_connection,
                                        required_permissions=alt_tool.required_permissions,
                                        db=db
                                    )
                                except Exception as ace:
                                    alt_creds = None

                            # Re-classify risk for recovery action
                            alt_risk = risk_classifier.assess_action(
                                capability_id=task.capability_id,
                                action=recovery_plan.updated_action or action_name,
                                params=recovery_plan.updated_params or action_params,
                                preferences=preferences
                            )

                            if alt_risk.requires_approval:
                                # Fresh approval required with new payload hash
                                alt_appr = Approval(
                                    execution_id=execution_id,
                                    task_id=task.id,
                                    action=recovery_plan.updated_action or action_name,
                                    target=alt_risk.target,
                                    content=recovery_plan.updated_params or action_params,
                                    payload_hash=alt_risk.payload_hash,
                                    reason=f"Recovery action: {alt_risk.reason}",
                                    risk=alt_risk.risk_level,
                                    consequences=alt_risk.consequences,
                                    status="pending"
                                )
                                db.add(alt_appr)
                                execution.status = "waiting_approval"
                                task.status = "waiting_approval"
                                await db.commit()

                                await event_broadcaster.emit(
                                    db, execution_id, "approval_required",
                                    f"Approval required for recovery action: {alt_risk.reason}",
                                    task_id=task.id,
                                    tool_id=alt_tool.id,
                                    payload={
                                        "approval_id": alt_appr.id,
                                        "action": alt_appr.action,
                                        "risk": alt_risk.risk_level,
                                        "content": alt_appr.content,
                                        "reason": alt_appr.reason
                                    }
                                )

                                # Wait for approval decision
                                while True:
                                    await asyncio.sleep(2.0)
                                    await db.refresh(alt_appr)
                                    if alt_appr.status in ["approved", "rejected", "expired"]:
                                        break
                                    await db.refresh(execution)
                                    if execution.status == "cancelled":
                                        return

                                if alt_appr.status != "approved":
                                    recovery.status = "failed"
                                    task.status = "rejected"
                                    execution.status = "stopped"
                                    execution.completed_at = datetime.now(timezone.utc)
                                    await db.commit()
                                    return

                                execution.status = "running"
                                task.status = "running"
                                await db.commit()

                            # Execute alternative tool
                            try:
                                alt_result = await alt_tool.execute(
                                    action=recovery_plan.updated_action or action_name,
                                    params=recovery_plan.updated_params or action_params,
                                    credentials=alt_creds
                                )
                                alt_v = await verification_engine.verify_task_outcome(
                                    capability_id=task.capability_id,
                                    action=recovery_plan.updated_action or action_name,
                                    params=recovery_plan.updated_params or action_params,
                                    result=alt_result,
                                    credentials=alt_creds,
                                    tool_id=alt_tool.id
                                )
                                if alt_v.result == "passed":
                                    recovery.status = "succeeded"
                                    task.status = "completed"
                                    task.selected_tool_id = alt_tool.id
                                    task.result = alt_result

                                    # Persist recovery verification entity
                                    v_rec = Verification(
                                        execution_id=execution_id,
                                        task_id=task.id,
                                        criterion=f"Verify recovered {recovery_plan.updated_action or action_name} outcome via {alt_tool.name}",
                                        result="passed",
                                        evidence=alt_v.evidence
                                    )
                                    db.add(v_rec)
                                    await db.commit()

                                    await event_broadcaster.emit(
                                        db, execution_id, "recovery_completed",
                                        f"Recovery successful using {alt_tool.name}.",
                                        task_id=task.id,
                                        tool_id=alt_tool.id,
                                        payload={"success": True, "evidence": redact_sensitive_data(alt_v.evidence)}
                                    )
                                    completed_count += 1
                                    continue
                            except Exception:
                                pass

                            recovery.status = "failed"
                            await db.commit()

                    # Recovery failed or no alternative available
                    task.status = "failed"
                    completed_count = len([t for t in tasks if t.status == "completed"])
                    execution.outcome = "PARTIALLY_COMPLETED" if completed_count > 0 else "FAILED"
                    execution.evidence_level = "ACTION_EXECUTED" if completed_count > 0 else "ACTION_REQUESTED"
                    execution.status = "failed"
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.outcome_summary = f"Task '{task.title}' failed: {redact_sensitive_data(problem_desc)}"
                    await db.commit()

                    await event_broadcaster.emit(
                        db, execution_id, "recovery_completed",
                        "No alternative recovery plan could complete the task. Stopping honestly as failed.",
                        task_id=task.id,
                        payload={"success": False}
                    )
                    await event_broadcaster.emit(
                        db, execution_id, "execution_failed",
                        f"Execution failed on Task {task.order}: {task.title}",
                        task_id=task.id,
                        payload={
                            "outcome": execution.outcome,
                            "evidence_level": execution.evidence_level,
                            "summary": execution.outcome_summary
                        }
                    )
                    return


                # Task completed normally
                task.status = "completed"
                completed_count += 1
                execution.progress = completed_count / total_tasks
                await db.commit()

                await event_broadcaster.emit(
                    db, execution_id, "task_completed",
                    f"Completed Task {task.order}: {task.title}",
                    task_id=task.id,
                    payload={"completed": completed_count, "total": total_tasks}
                )

            # All tasks finished — perform universal Goal-Level Verification
            understanding = goal.understanding or {}
            desired_outcome = understanding.get("desired_outcome")
            success_criteria = understanding.get("success_criteria", [])

            # Load all verifications recorded for this execution
            v_stmt = select(Verification).where(Verification.execution_id == execution_id)
            v_res = await db.execute(v_stmt)
            all_verifications = v_res.scalars().all()

            goal_v_result = await verification_engine.verify_goal_outcome(
                goal_text=goal.text,
                desired_outcome=desired_outcome,
                success_criteria=success_criteria,
                tasks=tasks,
                task_verifications=all_verifications
            )

            execution.outcome = goal_v_result.goal_outcome
            execution.evidence_level = goal_v_result.evidence_level
            execution.outcome_summary = goal_v_result.summary
            execution.status = "completed" if goal_v_result.goal_outcome == "COMPLETED" else "completed"
            execution.progress = 1.0
            execution.completed_at = datetime.now(timezone.utc)
            await db.commit()

            completed_time = execution.completed_at
            started_time = execution.started_at
            if completed_time and started_time:
                if completed_time.tzinfo is not None and started_time.tzinfo is None:
                    started_time = started_time.replace(tzinfo=timezone.utc)
                elif completed_time.tzinfo is None and started_time.tzinfo is not None:
                    completed_time = completed_time.replace(tzinfo=timezone.utc)
                duration_s = max(0.0, (completed_time - started_time).total_seconds())
            else:
                duration_s = 0.0

            summary_stats = {
                "tasks_completed": completed_count,
                "total_tasks": total_tasks,
                "tools_used": list(tools_used),
                "recoveries": recoveries_count,
                "approvals": approvals_count,
                "duration_seconds": round(duration_s, 1),
                "outcome": execution.outcome,
                "evidence_level": execution.evidence_level,
                "summary": execution.outcome_summary,
                "criteria_evaluations": [c.model_dump() for c in goal_v_result.criteria_evaluations]
            }

            await event_broadcaster.emit(
                db, execution_id, "execution_completed",
                f"Goal {execution.outcome.lower()}: {execution.outcome_summary}",
                payload=summary_stats
            )

execution_runner = ExecutionRunner()

