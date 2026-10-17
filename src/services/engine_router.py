from typing import Literal


Engine = Literal[
    "forge",
    "learn",
    "research",
    "explore",
    "solve",
]


ENGINE_ACTIONS = {
    "forge": {
        "create_project": "Create a new software or AI project.",
        "design_architecture": "Design the system architecture for a project.",
        "build_ai_agent": "Build an AI agent and define its components and workflow.",
    },
    "learn": {
        "start_learning_path": "Create a structured learning path for a technology or concept.",
        "explore_concept": "Explain and explore a technical concept deeply.",
        "practice": "Create practical exercises and guide the user through them.",
    },
    "research": {
        "start_research": "Define and structure a research topic.",
        "review_literature": "Analyze and organize research literature.",
        "design_experiment": "Design a research experiment, methodology, or evaluation.",
    },
    "explore": {
        "explore_technology": "Explore a technology, framework, tool, or technical domain.",
        "compare_approaches": "Compare technical approaches based on relevant criteria.",
        "discover_ideas": "Generate and investigate technical ideas and possibilities.",
    },
    "solve": {
        "define_problem": "Clarify and formalize an engineering problem.",
        "break_into_steps": "Break an engineering problem into actionable steps.",
        "work_through_solution": "Work through an engineering solution step by step.",
    },
}


def get_engine_instructions(
    engine: str | None,
    action: str | None,
) -> str:
    if not engine:
        return ""

    if engine not in ENGINE_ACTIONS:
        return ""

    engine_description = {
        "forge": "Build and create software, systems, APIs, and AI agents.",
        "learn": "Teach and develop technical knowledge through structured learning.",
        "research": "Support research, literature analysis, experiments, and technical investigation.",
        "explore": "Investigate technologies, approaches, tools, and technical ideas.",
        "solve": "Analyze engineering problems and develop practical solutions.",
    }[engine]

    action_description = None

    if action:
        action_description = ENGINE_ACTIONS[engine].get(action)

    instructions = [
        f"Active LATZ engine: {engine}.",
        f"Engine purpose: {engine_description}",
    ]

    if action_description:
        instructions.append(
            f"Active workflow: {action}. {action_description}"
        )

    instructions.append(
        "Keep the response aligned with the active engine and workflow."
    )

    return "\n".join(instructions)