import json
from typing import Any

from src.config.settings import settings
from src.services.tool_registry import execute_tool, get_tool_definitions


MAX_TOOL_ROUNDS = 3


def run_tool_calling(
    client: Any,
    messages: list[dict[str, Any]],
) -> str:
    conversation = list(messages)
    tools = get_tool_definitions()

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=conversation,
            max_tokens=1200,
            tools=tools,
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message
        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            return assistant_message.content or ""

        conversation.append(
            {
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ],
            }
        )

        for call in tool_calls:
            try:
                result = execute_tool(
                    call.function.name,
                    call.function.arguments,
                )
                tool_result = json.dumps(result, allow_nan=False)
            except (ValueError, TypeError, ArithmeticError) as exc:
                tool_result = json.dumps(
                    {"error": str(exc)[:300]},
                    allow_nan=False,
                )

            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": tool_result,
                }
            )

    final_response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=conversation,
        max_tokens=1200,
    )

    return final_response.choices[0].message.content or (
        "I couldn't complete the tool-assisted response within the execution limit."
    )
