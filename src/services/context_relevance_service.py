from typing import Any


ROLE_KEYWORDS = {
    "student": {
        "study",
        "exam",
        "assignment",
        "class",
        "college",
        "learning",
        "course",
        "subject",
    },
    "engineer": {
        "code",
        "coding",
        "software",
        "system",
        "architecture",
        "debug",
        "api",
        "backend",
        "frontend",
        "development",
        "engineering",
    },
    "ai engineer": {
        "ai",
        "artificial intelligence",
        "machine learning",
        "ml",
        "llm",
        "rag",
        "agent",
        "genai",
        "model",
        "embedding",
        "vector",
        "prompt",
    },
    "researcher": {
        "research",
        "paper",
        "publication",
        "experiment",
        "hypothesis",
        "dataset",
        "analysis",
        "literature",
        "research project",
    },
    "faculty": {
        "lecture",
        "teaching",
        "student",
        "mentoring",
        "class",
        "assignment",
        "grading",
        "course",
        "faculty",
        "academic",
    },
    "entrepreneur": {
        "business",
        "startup",
        "company",
        "customer",
        "client",
        "product",
        "revenue",
        "market",
        "founder",
    },
    "freelancer": {
        "freelance",
        "client",
        "proposal",
        "project",
        "payment",
        "gig",
        "contract",
    },
    "professional": {
        "career",
        "job",
        "work",
        "office",
        "manager",
        "promotion",
        "salary",
        "interview",
    },
}


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def keyword_score(text: str, keywords: set[str]) -> int:
    normalized = normalize_text(text)

    score = 0

    for keyword in keywords:
        if keyword in normalized:
            score += 1

    return score


def score_role_relevance(
    message: str,
    role: dict[str, Any],
) -> int:
    role_name = normalize_text(role.get("role", ""))

    keywords = ROLE_KEYWORDS.get(role_name, set())

    if not keywords:
        return 0

    return keyword_score(message, keywords)


def score_goal_relevance(
    message: str,
    goal: dict[str, Any],
) -> int:
    searchable_text = " ".join(
        [
            str(goal.get("title") or ""),
            str(goal.get("description") or ""),
            str(goal.get("category") or ""),
        ]
    )

    return keyword_score(message, set(normalize_text(searchable_text).split()))


def score_memory_relevance(
    message: str,
    memory: dict[str, Any],
) -> int:
    memory_text = str(memory.get("content") or "")

    return keyword_score(
        message,
        set(normalize_text(memory_text).split()),
    )


def select_relevant_context(
    message: str,
    context: dict[str, Any] | None,
    max_roles: int = 3,
    max_goals: int = 5,
    max_memories: int = 5,
) -> dict[str, Any]:
    if not context:
        return {
            "profile": None,
            "life_roles": [],
            "goals": [],
            "memories": [],
        }

    roles = context.get("life_roles", [])
    goals = context.get("goals", [])
    memories = context.get("memories", [])

    scored_roles = [
        (
            score_role_relevance(message, role),
            role.get("priority", 1),
            role,
        )
        for role in roles
    ]

    scored_goals = [
        (
            score_goal_relevance(message, goal),
            goal.get("priority", 1),
            goal,
        )
        for goal in goals
    ]

    scored_memories = [
        (
            score_memory_relevance(message, memory),
            memory,
        )
        for memory in memories
    ]

    relevant_roles = [
        role
        for score, priority, role in sorted(
            scored_roles,
            key=lambda item: (-item[0], item[1]),
        )
        if score > 0
    ][:max_roles]

    relevant_goals = [
        goal
        for score, priority, goal in sorted(
            scored_goals,
            key=lambda item: (-item[0], item[1]),
        )
        if score > 0
    ][:max_goals]

    relevant_memories = [
        memory
        for score, memory in sorted(
            scored_memories,
            key=lambda item: -item[0],
        )
        if score > 0
    ][:max_memories]

    if not relevant_roles and roles:
        relevant_roles = sorted(
            roles,
            key=lambda role: role.get("priority", 1),
        )[:1]

    return {
        "profile": context.get("profile"),
        "life_roles": relevant_roles,
        "goals": relevant_goals,
        "memories": relevant_memories,
    }