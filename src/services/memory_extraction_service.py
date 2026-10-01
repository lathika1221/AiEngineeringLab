import re


PREFERENCE_PATTERNS = [
    r"\bi prefer\b",
    r"\bi always prefer\b",
    r"\bi like\b",
    r"\bi usually use\b",
    r"\bi always use\b",
    r"\bi want you to\b",
    r"\bmy preference is\b",
]

FACT_PATTERNS = [
    r"\bi am\b",
    r"\bi'm\b",
    r"\bi work with\b",
    r"\bi use\b",
    r"\bi have\b",
    r"\bi know\b",
]

PROJECT_PATTERNS = [
    r"\bi am building\b",
    r"\bi'm building\b",
    r"\bmy project is\b",
    r"\bmy final year project is\b",
    r"\bthe project is\b",
]


def normalize_memory_content(content: str) -> str:
    text = content.strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = text.rstrip(" .!?")

    return text


def build_memory_key(
    memory_type: str,
    content: str,
) -> str:
    normalized = normalize_memory_content(
        content
    )

    return (
        f"{memory_type}:"
        f"{normalized.lower()}"
    )


def detect_memory_candidate(message: str):
    text = message.strip()

    if not text:
        return None

    memory_type = None

    for pattern in PREFERENCE_PATTERNS:
        if re.search(
            pattern,
            text,
            re.IGNORECASE,
        ):
            memory_type = "preference"
            break

    if memory_type is None:
        for pattern in PROJECT_PATTERNS:
            if re.search(
                pattern,
                text,
                re.IGNORECASE,
            ):
                memory_type = "project"
                break

    if memory_type is None:
        for pattern in FACT_PATTERNS:
            if re.search(
                pattern,
                text,
                re.IGNORECASE,
            ):
                memory_type = "fact"
                break

    if memory_type is None:
        return None

    normalized_content = normalize_memory_content(
        text
    )

    return {
        "memory_type": memory_type,
        "content": normalized_content,
        "memory_key": build_memory_key(
            memory_type,
            normalized_content,
        ),
    }
