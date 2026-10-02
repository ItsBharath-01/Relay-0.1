import inspect
import pytest
import jsonschema

from app.tools.registry import get_all_tools
from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)
from app.tools.adapters.mcp_adapter import DynamicMCPTool


@pytest.mark.unit
def test_all_tools_identical_signatures():
    """Verify that every tool adapter in get_all_tools() conforms to the exact canonical signatures."""
    tools = get_all_tools()
    assert len(tools) >= 9, f"Expected at least 9 registered tools, found {len(tools)}"

    expected_execute_params = ["action", "params", "ctx"]
    expected_verify_params = ["action", "params", "result", "ctx"]

    for tool in tools:
        # Check execute signature (bound method)
        exec_sig = inspect.signature(tool.execute)
        exec_param_names = list(exec_sig.parameters.keys())
        assert exec_param_names == expected_execute_params, (
            f"Tool '{tool.id}' execute signature mismatch: {exec_param_names} != {expected_execute_params}"
        )

        # Check verify signature (bound method)
        ver_sig = inspect.signature(tool.verify)
        ver_param_names = list(ver_sig.parameters.keys())
        assert ver_param_names == expected_verify_params, (
            f"Tool '{tool.id}' verify signature mismatch: {ver_param_names} != {expected_verify_params}"
        )


@pytest.mark.unit
def test_dynamic_mcp_tool_conforms_to_canonical_signature():
    """Verify that DynamicMCPTool instances conform to the exact canonical signatures."""
    dynamic_tool = DynamicMCPTool(
        connection_id="conn-test",
        server_name="TestMCP",
        tool_name="test_tool",
        description="A test MCP tool",
        input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        capability_id="mcp_test"
    )

    expected_execute_params = ["action", "params", "ctx"]
    expected_verify_params = ["action", "params", "result", "ctx"]

    exec_sig = inspect.signature(dynamic_tool.execute)
    assert list(exec_sig.parameters.keys()) == expected_execute_params

    ver_sig = inspect.signature(dynamic_tool.verify)
    assert list(ver_sig.parameters.keys()) == expected_verify_params


@pytest.mark.unit
def test_all_tools_action_specs_and_valid_param_schemas():
    """Verify that every tool declares valid ActionSpecs with compliant JSON schemas."""
    tools = get_all_tools()
    
    # Also include a DynamicMCPTool
    tools.append(
        DynamicMCPTool(
            connection_id="conn-1",
            server_name="NotesServer",
            tool_name="create_note",
            description="Create a note",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
            capability_id="note_create"
        )
    )

    for tool in tools:
        specs = tool.describe_actions()
        assert isinstance(specs, list), f"Tool '{tool.id}' describe_actions() must return a list"
        assert len(specs) > 0, f"Tool '{tool.id}' has no ActionSpecs declared"

        for spec in specs:
            assert isinstance(spec, ActionSpec), f"Tool '{tool.id}' declared item is not an ActionSpec"
            assert isinstance(spec.action, str) and len(spec.action) > 0
            assert isinstance(spec.capability_id, str) and len(spec.capability_id) > 0
            assert isinstance(spec.effect_class, EffectClass)
            assert isinstance(spec.param_schema, dict)

            # JSON Schema draft validation
            try:
                jsonschema.Draft7Validator.check_schema(spec.param_schema)
            except jsonschema.SchemaError as e:
                pytest.fail(f"Tool '{tool.id}' action '{spec.action}' has invalid param_schema: {e}")


@pytest.mark.unit
def test_tool_result_contract():
    """Verify ToolResult structured properties and dict-like compatibility."""
    res = ToolResult(
        status="success",
        data={"items": [1, 2, 3], "count": 3},
        error=None,
        side_effect_state="CONFIRMED",
        external_ids=["id-123"]
    )

    # Structured access
    assert res.status == "success"
    assert res.side_effect_state == "CONFIRMED"
    assert res.external_ids == ["id-123"]

    # Dict-like access
    assert res["count"] == 3
    assert res.get("items") == [1, 2, 3]
    assert "count" in res
    assert res.get("nonexistent", "default") == "default"
    assert res["status"] == "success"
    assert res["side_effect_state"] == "CONFIRMED"

    # Conversion
    d = res.to_dict()
    assert isinstance(d, dict)
    assert d["count"] == 3
    assert d["status"] == "success"


@pytest.mark.unit
def test_verification_outcome_contract():
    """Verify VerificationOutcome structured properties and tuple-unpacking compatibility."""
    outcome = VerificationOutcome(
        result="passed",
        evidence={"observed_id": "item-1"},
        reason="Item verified in external store"
    )

    # Structured access
    assert outcome.result == "passed"
    assert outcome.evidence["observed_id"] == "item-1"
    assert outcome.reason == "Item verified in external store"

    # Tuple unpacking compatibility: passed, evidence = outcome
    passed, evidence = outcome
    assert passed is True
    assert evidence == {"observed_id": "item-1"}
