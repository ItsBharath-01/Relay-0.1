import pytest
from app.schemas.recovery import FailureDiagnosis, RecoveryPlan
from app.recovery.engine import recovery_engine
from app.tools.registry.capabilities import get_valid_capability_ids

def test_classify_transient_error():
    assert recovery_engine.classify_transient_error("HTTP 504 Gateway Timeout") == "timeout"
    assert recovery_engine.classify_transient_error("Error 429 Too Many Requests") == "rate_limit"
    assert recovery_engine.classify_transient_error("HTTP 502 Bad Gateway") == "network"
    assert recovery_engine.classify_transient_error("Invalid parameters provided") is None

@pytest.mark.asyncio
async def test_diagnose_failure_deterministic_transient():
    diag = await recovery_engine.diagnose_failure(
        task_id="task_1",
        task_title="Search web",
        capability_id="web_search",
        problem="Request timed out after 30.0s",
        attempt=1
    )
    assert diag.failure_type == "timeout"
    assert diag.recoverable is True
    assert diag.recommended_strategy == "retry_with_backoff"

@pytest.mark.asyncio
async def test_diagnose_failure_revoked_auth():
    diag = await recovery_engine.diagnose_failure(
        task_id="task_2",
        task_title="Read calendar",
        capability_id="calendar_read",
        problem="Google token revoked. Please reconnect.",
        attempt=1
    )
    assert diag.failure_type == "auth"
    assert diag.recoverable is False
    assert diag.recommended_strategy == "reconnect_required"

def test_validate_recovery_plan():
    valid_caps = get_valid_capability_ids()
    
    # Valid plan
    valid_plan = RecoveryPlan(
        strategy="alternative_tool",
        alternative_capability="web_search",
        alternative_tool="web_search_engine",
        reason="Primary failed",
        expected_result="Search succeeds"
    )
    assert recovery_engine.validate_plan(valid_plan, valid_caps) is True

    # Invalid strategy
    invalid_strategy_plan = RecoveryPlan(
        strategy="hack_system",
        alternative_capability="web_search",
        reason="Test",
        expected_result="Test"
    )
    assert recovery_engine.validate_plan(invalid_strategy_plan, valid_caps) is False

    # Invalid capability
    invalid_cap_plan = RecoveryPlan(
        strategy="alternative_tool",
        alternative_capability="super_secret_unregistered_cap",
        reason="Test",
        expected_result="Test"
    )
    assert recovery_engine.validate_plan(invalid_cap_plan, valid_caps) is False
