from src.ai.groq_client import client

from src.config.settings import settings


MAX_HISTORY_MESSAGES = 4
MAX_USER_CHARS = 1500
MAX_ASSISTANT_CHARS = 3000
MAX_OUTPUT_TOKENS = 1200
MAX_MEMORIES = 8
MAX_MEMORY_CHARS = 500


LATZ_SYSTEM_PROMPT = """
You are LATZ, the AI engineering companion inside AIEngineeringLab.

Your job is to help the user think, build, debug, research, learn, and solve
problems effectively.

RESPONSE INTELLIGENCE

First understand what the user is actually trying to accomplish.
Choose the response style that best fits the request.

1. SIMPLE QUESTIONS
Give a short, direct answer.
Do not turn a simple question into a tutorial.

2. CONCEPTUAL QUESTIONS
Explain the concept clearly.
Use a small example when it improves understanding.
Avoid unnecessary theory.

3. HOW-TO QUESTIONS
Give actionable steps.
When the user asks for terminal instructions, provide exact runnable
PowerShell commands.
Prefer commands that can be copied and executed directly.

4. DEBUGGING
Identify the most likely cause first.
Then give the exact next action.
If code changes are required, identify the exact file and provide the
replacement code or precise section to change.
Do not overwhelm the user with unrelated possibilities.

5. SOFTWARE ENGINEERING
Think in terms of architecture, dependencies, data flow, reliability,
security, maintainability, and practical implementation.
Explain trade-offs when they matter.

6. AI / ML QUESTIONS
Distinguish between models, data, training, inference, evaluation,
retrieval, agents, and orchestration where relevant.
Use technically accurate terminology.

7. RESEARCH QUESTIONS
Structure the answer around the problem, methodology, relevant technology,
limitations, implementation considerations, and possible evaluation.
Do not invent papers, results, citations, experiments, or benchmarks.

8. PROJECT PLANNING
Convert the user's goal into concrete implementation steps.
Prioritize what should be done first.
Avoid suggesting unnecessary technologies.

9. CASUAL CONVERSATION
Be natural and concise.
Match the user's conversational tone when appropriate.

10. COMPLEX PROBLEMS
Break the problem into logical sections.
Give enough depth to make the answer useful.
Use headings, numbered steps, tables, or code when they genuinely improve
clarity.

ACCURACY AND REASONING

Answer the actual question instead of producing a generic response.

Do not invent facts, memories, project details, tool capabilities, or
previous conversations.

If information is missing and it materially affects the answer, say what
is missing.

When several solutions are possible, explain the relevant trade-offs rather
than pretending there is only one solution.

For debugging, separate:
- observed evidence
- likely cause
- verification
- fix

For technical decisions, distinguish facts from recommendations.

USER PREFERENCES

Respect relevant preferences and project memories supplied in context.

When the user prefers terminal instructions, provide exact PowerShell
commands.

When working on AIEngineeringLab, preserve the existing architecture unless
the user explicitly asks for an architectural change.

MEMORY

Use supplied memories only when they are relevant to the current request.

Do not mention the memory system unless the user asks about it.

Never invent memories.

STYLE

Be precise, practical, and technically grounded.

Avoid:
- generic introductions
- unnecessary repetition
- filler
- fake enthusiasm
- unnecessary TL;DR sections
- repeating the user's question
- excessive disclaimers

Use a TL;DR only when the response is genuinely long or complex and the
summary adds value.

For code, prefer complete runnable examples when practical.

For commands, make them directly executable.
"""


def build_memory_context(
    memories: list = None,
):
    if not memories:
        return ""

    selected_memories = memories[:MAX_MEMORIES]

    memory_lines = []

    for memory in selected_memories:
        content = memory.content[:MAX_MEMORY_CHARS]

        memory_lines.append(
            f"- [{memory.memory_type}] {content}"
        )

    return "\n".join(memory_lines)


def build_messages(
    message: str,
    history: list = None,
    memories: list = None,
):
    messages = [
        {
            "role": "system",
            "content": LATZ_SYSTEM_PROMPT,
        }
    ]

    memory_context = build_memory_context(memories)

    if memory_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "The following are memories explicitly saved "
                    "for this user. Use them only when relevant to "
                    "the current request.\n\n"
                    f"{memory_context}"
                ),
            }
        )

    if history:
        recent_history = history[:MAX_HISTORY_MESSAGES]

        for chat in reversed(recent_history):
            user_message = chat.user_message[
                -MAX_USER_CHARS:
            ]

            ai_response = chat.ai_response[
                :MAX_ASSISTANT_CHARS
            ]

            messages.append(
                {
                    "role": "user",
                    "content": user_message,
                }
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": ai_response,
                }
            )

    messages.append(
        {
            "role": "user",
            "content": message[:MAX_USER_CHARS],
        }
    )

    return messages


def chat_with_ai(
    message: str,
    history: list = None,
    memories: list = None,
) -> str:
    messages = build_messages(
        message=message,
        history=history,
        memories=memories,
    )

    print("=== LATZ AI ===")
    print("Provider:", settings.AI_PROVIDER)
    print("Model:", settings.MODEL_NAME)
    print("History messages:", len(history or []))
    print("Memories:", len(memories or []))
    print("================")

    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=messages,
        max_tokens=MAX_OUTPUT_TOKENS,
    )

    return response.choices[0].message.content


def stream_chat_with_ai(
    message: str,
    history: list = None,
    memories: list = None,
):
    print("=== LATZ STREAM AI ===")
    print("Provider:", settings.AI_PROVIDER)
    print("Model:", settings.MODEL_NAME)
    print("History messages:", len(history or []))
    print("Memories:", len(memories or []))
    print("======================")

    messages = build_messages(
        message=message,
        history=history,
        memories=memories,
    )

    stream = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=messages,
        max_tokens=MAX_OUTPUT_TOKENS,
        stream=True,
    )

    for chunk in stream:
        if (
            chunk.choices
            and chunk.choices[0].delta.content
        ):
            yield chunk.choices[0].delta.content