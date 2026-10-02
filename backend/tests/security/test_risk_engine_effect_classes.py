import pytest
from app.risk.classifier import risk_classifier, RiskAssessment
from app.models.entities import UserPreference
from app.tools.registry.base import EffectClass, ActionSpec
from app.tools.registry import register_tool, unregister_tool, BaseTool, ToolResult, VerificationOutcome
from typing import List, Dict, Any, Optional, Tuple

class DummyTool(BaseTool):
    id = "dummy_test_tool"
    name = "Dummy Test Tool"
    tool_type = "api"
    provides = ["dummy_action"]
    requires_connection = None
    required_permissions = []

    def __init__(self, action_specs: List[ActionSpec]):
        self._action_specs = action_specs

    def describe_actions(self) -> List[ActionSpec]:
        return self._action_specs

    async def execute(self, action: str, params: Dict[str, Any], ctx: Any) -> ToolResult:
        return ToolResult(status="success")

    async def verify(self, action: str, params: Dict[str, Any], result: Any, ctx: Any) -> VerificationOutcome:
        return VerificationOutcome(result="passed")

    async def health_check(self, credentials: Any = None) -> Tuple[bool, str]:
        return True, "Dummy tool healthy"


def test_effect_class_read_only_low_risk_no_approval():
    """Verify that READ_ONLY actions evaluate to low risk and require no approval."""
    spec = ActionSpec(
        action="inspect_data",
        capability_id="data_read",
        effect_class=EffectClass.READ_ONLY
    )
    tool = DummyTool([spec])
    register_tool(tool)
    try:
        assessment = risk_classifier.assess_action(
            capability_id="data_read",
            action="inspect_data",
            params={"id": "123"},
            action_spec=spec
        )
        assert assessment.risk_level == "low"
        assert assessment.requires_approval is False
    finally:
        unregister_tool("dummy_test_tool")


def test_effect_class_irreversible_critical_risk_requires_approval():
    """Verify that IRREVERSIBLE actions evaluate to critical risk and require approval."""
    spec = ActionSpec(
        action="purge_database",
        capability_id="db_purge",
        effect_class=EffectClass.IRREVERSIBLE
    )
    assessment = risk_classifier.assess_action(
        capability_id="db_purge",
        action="purge_database",
        params={"target": "all"},
        action_spec=spec
    )
    assert assessment.risk_level == "critical"
    assert assessment.requires_approval is True


def test_effect_class_non_idempotent_write_requires_approval_by_default():
    """Verify that NON_IDEMPOTENT_WRITE requires approval and evaluates to high risk."""
    spec = ActionSpec(
        action="create_external_lead",
        capability_id="lead_create",
        effect_class=EffectClass.NON_IDEMPOTENT_WRITE
    )
    assessment = risk_classifier.assess_action(
        capability_id="lead_create",
        action="create_external_lead",
        params={"name": "Alice"},
        action_spec=spec
    )
    assert assessment.risk_level in ["high", "medium"]
    assert assessment.requires_approval is True


def test_mcp_unknown_tool_defaults_to_write_approval():
    """Verify that MCP tool with unknown effect defaults to requiring approval."""
    # MCP tool without known spec
    assessment = risk_classifier.assess_action(
        capability_id="custom_unknown_mcp_capability",
        action="unknown_mcp_tool",
        params={"arg1": "val1"},
        action_spec=None
    )
    assert assessment.requires_approval is True
    assert assessment.risk_level in ["high", "medium"]
