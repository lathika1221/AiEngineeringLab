from types import SimpleNamespace
from unittest.mock import MagicMock

from src.services import tool_calling_service


def make_response(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls or [],
                )
            )
        ]
    )


def make_tool_call(name, arguments, call_id="call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def test_returns_normal_model_response(monkeypatch):
    monkeypatch.setattr(tool_calling_service.settings, "MODEL_NAME", "test-model")
    client = MagicMock()
    client.chat.completions.create.return_value = make_response("Hello")

    result = tool_calling_service.run_tool_calling(
        client,
        [{"role": "user", "content": "Hello"}],
    )

    assert result == "Hello"
    assert client.chat.completions.create.call_count == 1


def test_executes_allowlisted_tool_and_returns_final_response(monkeypatch):
    monkeypatch.setattr(tool_calling_service.settings, "MODEL_NAME", "test-model")
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        make_response(
            tool_calls=[
                make_tool_call(
                    "calculate",
                    '{"expression": "(12 + 8) * 3"}',
                )
            ]
        ),
        make_response("The answer is 60."),
    ]

    result = tool_calling_service.run_tool_calling(
        client,
        [{"role": "user", "content": "Calculate (12 + 8) * 3"}],
    )

    assert result == "The answer is 60."
    assert client.chat.completions.create.call_count == 2
    second_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert '"result": 60' in second_messages[-1]["content"]


def test_invalid_tool_arguments_return_error_to_model(monkeypatch):
    monkeypatch.setattr(tool_calling_service.settings, "MODEL_NAME", "test-model")
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        make_response(
            tool_calls=[
                make_tool_call(
                    "calculate",
                    '{"expression": "1 + 1", "extra": true}',
                )
            ]
        ),
        make_response("I could not run that calculation."),
    ]

    result = tool_calling_service.run_tool_calling(
        client,
        [{"role": "user", "content": "Calculate"}],
    )

    assert result == "I could not run that calculation."
    second_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert '"error"' in second_messages[-1]["content"]


def test_tool_loop_is_bounded_and_returns_fallback(monkeypatch):
    monkeypatch.setattr(tool_calling_service.settings, "MODEL_NAME", "test-model")
    client = MagicMock()
    repeated_tool_response = make_response(
        tool_calls=[
            make_tool_call("calculate", '{"expression": "1 + 1"}')
        ]
    )
    client.chat.completions.create.side_effect = [
        repeated_tool_response,
        repeated_tool_response,
        repeated_tool_response,
        make_response(None),
    ]

    result = tool_calling_service.run_tool_calling(
        client,
        [{"role": "user", "content": "Calculate"}],
    )

    assert "execution limit" in result
    assert client.chat.completions.create.call_count == (
        tool_calling_service.MAX_TOOL_ROUNDS + 1
    )
