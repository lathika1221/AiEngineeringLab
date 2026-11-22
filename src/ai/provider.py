from src.config.settings import PRODUCTION_AI_PROVIDER, settings


def get_ai_client():
    provider = settings.AI_PROVIDER.strip().lower()

    # Defence in depth: Settings already refuses a non-Groq provider at startup in
    # production. This re-checks at call time so a provider changed after startup
    # still cannot reach a paid API. There is deliberately no fallback to another
    # provider: the configured one is used, or the call fails.
    if settings.is_production and provider != PRODUCTION_AI_PROVIDER:
        raise ValueError(
            f"AI_PROVIDER {provider!r} is not permitted in production; "
            f"only {PRODUCTION_AI_PROVIDER!r} is allowed."
        )

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
