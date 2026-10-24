import pytest

from src.services.tool_registry import (
    execute_tool,
    get_tool_definitions,
)


def test_calculate_basic_expression():
    result = execute_tool(
        "calculate",
        {"expression": "(12 + 8) * 3"},
    )
    assert result["result"] == 60


def test_calculate_division():
    result = execute_tool(
        "calculate",
        {"expression": "10 / 4"},
    )
    assert result["result"] == 2.5


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError, match="Unknown tool"):
        execute_tool("run_command", {"expression": "1 + 1"})


def test_extra_arguments_are_rejected():
    with pytest.raises(ValueError, match="Invalid arguments"):
        execute_tool(
            "calculate",
            {"expression": "1 + 1", "command": "whoami"},
        )


def test_code_execution_is_rejected():
    with pytest.raises(ValueError, match="Only basic arithmetic"):
        execute_tool(
            "calculate",
            {"expression": "__import__('os').system('whoami')"},
        )


def test_invalid_json_is_rejected():
    with pytest.raises(ValueError, match="valid JSON"):
        execute_tool("calculate", "{invalid json}")


def test_tool_definitions_are_available():
    definitions = get_tool_definitions()
    assert len(definitions) == 1
    assert definitions[0]["function"]["name"] == "calculate"


def test_calculate_rejects_excessive_expression_complexity():
    expression = "+".join(["1"] * 35)
    with pytest.raises(ValueError, match="complexity limit"):
        execute_tool("calculate", {"expression": expression})


def test_calculate_rejects_deeply_nested_expression():
    expression = "(" * 60 + "1" + ")" * 60
    with pytest.raises(ValueError, match="nesting limit"):
        execute_tool("calculate", {"expression": expression})
