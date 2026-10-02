import asyncio
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

from app.core.database import async_session_maker, init_db
from app.models.entities import Execution, Goal, Plan, User
from app.agent.execution_runner import execution_runner


def _uid():
    return uuid.uuid4().hex[:12]


@pytest.mark.integration
async def test_supervised_runner_handles_crash_gracefully():
    tag = _uid()
    user_id = f"test-runner-u1-{tag}"
    goal_id = f"g-crash-{tag}"
    plan_id = f"p-crash-{tag}"
    exec_id = f"exec-crash-{tag}"

    await init_db()
    async with async_session_maker() as db:
        user = User(id=user_id, name="Runner 1", email=f"runner1-{tag}@example.com", hashed_password="pw")
        goal = Goal(id=goal_id, user_id=user.id, text="Crash test goal")
        plan = Plan(id=plan_id, goal_id=goal.id, tasks=[])
        execution = Execution(
            id=exec_id,
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="pending"
        )
        db.add_all([user, goal, plan, execution])
        await db.commit()

    # Simulate an unhandled exception inside run_execution
    with patch.object(execution_runner, "run_execution", side_effect=RuntimeError("Simulated unhandled runner crash with token ya29.secret")):
        await execution_runner.start_execution_background(exec_id)
        # Give the event loop time to process task done callback and failure handler
        await asyncio.sleep(0.5)

    async with async_session_maker() as db:
        res = await db.get(Execution, exec_id)
        assert res is not None
        assert res.status == "failed"
        assert res.outcome == "FAILED"
        assert "Simulated unhandled runner crash" in res.outcome_summary
        # Redaction check: secrets must not appear in outcome_summary
        assert "ya29.secret" not in res.outcome_summary
        assert "[REDACTED_GOOGLE_TOKEN]" in res.outcome_summary


@pytest.mark.integration
async def test_cleanup_orphaned_executions():
    tag = _uid()
    user_id = f"test-runner-u2-{tag}"
    goal_id = f"g-stuck-{tag}"
    plan_id = f"p-stuck-{tag}"
    exec_id = f"exec-stuck-{tag}"

    await init_db()
    async with async_session_maker() as db:
        user = User(id=user_id, name="Runner 2", email=f"runner2-{tag}@example.com", hashed_password="pw")
        goal = Goal(id=goal_id, user_id=user.id, text="Stuck test goal")
        plan = Plan(id=plan_id, goal_id=goal.id, tasks=[])
        stuck_exec = Execution(
            id=exec_id,
            goal_id=goal.id,
            plan_id=plan.id,
            user_id=user.id,
            status="running"
        )
        db.add_all([user, goal, plan, stuck_exec])
        await db.commit()

    await execution_runner.cleanup_orphaned_executions()

    async with async_session_maker() as db:
        res = await db.get(Execution, exec_id)
        assert res is not None
        assert res.status == "failed"
        assert "server restart" in res.outcome_summary.lower()
