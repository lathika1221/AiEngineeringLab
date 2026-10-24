from src.config.settings import settings


def get_ai_client():
    provider = settings.AI_PROVIDER.strip().lower()

    if provider == "groq":
        from src.ai.groq_client import client
        return client

    if provider == "openai":
        from src.ai.openai_client import client
        return client

    raise ValueError(
        f"Unsupported AI_PROVIDER: {settings.AI_PROVIDER!r}. "
        "Supported providers are 'groq' and 'openai'."
    )
