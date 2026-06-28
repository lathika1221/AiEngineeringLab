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