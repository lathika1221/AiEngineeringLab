from openai import OpenAI

from src.config.settings import settings


client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
)
