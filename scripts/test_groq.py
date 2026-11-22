"""Manual smoke test for the Groq provider. Makes ONE live API call.

Run deliberately from the repository root, with the real key configured in your
environment:    python -m scripts.test_groq

Importing this module does nothing: no client is created and no request is made.
It is not a pytest test (pytest only collects ``tests/``).
"""


def main() -> None:
    # Imported here, not at module level, so that importing this file has no side effects
    # (the client is created at import time in src.ai.groq_client and needs the API key).
    from src.ai.groq_client import client
    from src.config.settings import settings

    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant for AIEngineeringLab."
            },
            {
                "role": "user",
                "content": "Introduce yourself in one sentence."
            },
        ],
    )

    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
