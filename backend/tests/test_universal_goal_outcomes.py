"""
test_universal_goal_outcomes.py — Tests for universal goal evaluation, evidence levels,
and separate goal/task outcome statuses.
"""
import pytest
from unittest.mock import MagicMock
from app.schemas.goal import GoalUnderstanding, ClarificationQuestion
from app.schemas.verification import GoalVerificationResult, GoalCriterionEvaluation
from app.verification.engine import VerificationEngine

pytestmark = pytest.mark.asyncio

def make_task(task_id: str, status: str = "completed"):
    t = MagicMock()
    t.id = task_id
    t.status = status
    return t

def make_verification(task_id: str, result: str = "passed", evidence: dict = None):
    v = MagicMock()
    v.task_id = task_id
    v.result = result
    v.evidence = evidence or {}
    v.criterion = "Test Criterion"
    return v

async def test_goal_understanding_desired_outcome_and_criteria():
    """Validates that GoalUnderstanding parses desired_outcome, success_criteria, and normalizes strings in clarification_questions."""
    gu = GoalUnderstanding.model_validate({
        "objective": "Play Tamil music",
        "intent": "play_music",
        "entities": {"genre": "Tamil music"},
        "constraints": [],
        "required_capabilities": ["browser_navigate"],
        "clarification_needed": True,
        "clarification_questions": ["Which artist do you prefer?", "Any specific song?"],
        "desired_outcome": "Tamil music track playing in active audio player",
        "success_criteria": ["Music audio stream active", "Playback controls visible"]
    })

    assert gu.desired_outcome == "Tamil music track playing in active audio player"
    assert len(gu.success_criteria) == 2
    assert len(gu.clarification_questions) == 2
    assert isinstance(gu.clarification_questions[0], ClarificationQuestion)
    assert gu.clarification_questions[0].question == "Which artist do you prefer?"


async def test_verify_goal_outcome_all_achieved():
    engine = VerificationEngine()
    t1 = make_task("task-1", "completed")
    t2 = make_task("task-2", "completed")
    v1 = make_verification("task-1", "passed", {"temp": 65})
    v2 = make_verification("task-2", "passed", {"display": True})

    result = await engine.verify_goal_outcome(
        goal_text="Check weather forecast",
        desired_outcome="Receive accurate tomorrow weather for Seattle",
        success_criteria=["Seattle forecast returned", "Temperature displayed"],
        tasks=[t1, t2],
        task_verifications=[v1, v2]
    )

    assert result.goal_outcome == "COMPLETED"
    assert result.evidence_level == "GOAL_ACHIEVED"
    assert len(result.criteria_evaluations) == 2
    assert all(c.status == "met" for c in result.criteria_evaluations)


async def test_verify_goal_outcome_blocked_when_no_tasks_succeeded():
    engine = VerificationEngine()
    t1 = make_task("task-1", "pending")

    result = await engine.verify_goal_outcome(
        goal_text="Play a song",
        desired_outcome="Audio playing",
        success_criteria=["Player active"],
        tasks=[t1],
        task_verifications=[],
        terminal_reason="blocked"
    )

    assert result.goal_outcome == "BLOCKED"
    assert result.evidence_level == "ACTION_REQUESTED"


async def test_verify_goal_outcome_partially_completed():
    engine = VerificationEngine()
    t1 = make_task("task-1", "completed")
    t2 = make_task("task-2", "failed")
    v1 = make_verification("task-1", "passed", {"count": 3})

    result = await engine.verify_goal_outcome(
        goal_text="Find and book a flight",
        desired_outcome="Flight found and booked",
        success_criteria=["Flights listed", "Booking confirmed"],
        tasks=[t1, t2],
        task_verifications=[v1]
    )

    assert result.goal_outcome == "PARTIALLY_COMPLETED"
    assert result.evidence_level == "ACTION_EXECUTED"


async def test_verify_goal_outcome_action_executed_without_independent_verification():
    engine = VerificationEngine()
    t1 = make_task("task-1", "completed")
    v1 = make_verification("task-1", "not_verifiable", {"status": "dispatched"})

    result = await engine.verify_goal_outcome(
        goal_text="Play Tamil music",
        desired_outcome="Music audio playing",
        success_criteria=["Audio stream active"],
        tasks=[t1],
        task_verifications=[v1]
    )

    assert result.evidence_level == "ACTION_EXECUTED"
    assert result.goal_outcome == "PARTIALLY_COMPLETED"
    assert result.criteria_evaluations[0].status == "not_verifiable"
