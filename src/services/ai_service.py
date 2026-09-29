from src.ai.groq_client import client
from src.config.settings import settings


def chat_with_ai(
    message: str,
    history: list = None,
) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are an AI assistant for AIEngineeringLab.",
        }
    ]

    if history:
        for chat in history:
            messages.append(
                {
                    "role": "user",
                    "content": chat.user_message,
                }
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": chat.ai_response,
                }
            )

    messages.append(
        {
            "role": "user",
            "content": message,
        }
    )

    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=messages,
    )

    return response.choices[0].message.content

def stream_chat_with_ai(
    message: str,
    history: list = None,
):
    messages = [
        {
            "role": "system",
            "content": "You are an AI assistant for AIEngineeringLab.",
        }
    ]

    if history:
        for chat in history:
            messages.append(
                {
                    "role": "user",
                    "content": chat.user_message,
                }
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": chat.ai_response,
                }
            )

    messages.append(
        {
            "role": "user",
            "content": message,
        }
    )

    stream = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=messages,
        stream=True,
    )

    for chunk in stream:
        if (
            chunk.choices
            and chunk.choices[0].delta.content
        ):
            yield chunk.choices[0].delta.content