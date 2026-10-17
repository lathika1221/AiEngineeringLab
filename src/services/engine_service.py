from typing import Any


ENGINE_WORKFLOWS: dict[str, dict[str, dict[str, Any]]] = {
    "forge": {
        "create_project": {
            "title": "Create New Project",
            "objective": (
                "Turn an initial idea into a concrete engineering project."
            ),
            "process": [
                "Clarify the project objective.",
                "Identify users or system consumers.",
                "Define the core features.",
                "Recommend an appropriate technology stack.",
                "Define the first implementation milestone.",
            ],
            "output": [
                "Project definition",
                "Core requirements",
                "Recommended stack",
                "Initial architecture",
                "Implementation milestones",
            ],
        },
        "design_architecture": {
            "title": "Design System Architecture",
            "objective": (
                "Design a practical and maintainable architecture "
                "for the user's system."
            ),
            "process": [
                "Identify system requirements.",
                "Identify major components.",
                "Define component responsibilities.",
                "Define data flow and communication.",
                "Identify storage and external services.",
                "Identify security and reliability considerations.",
            ],
            "output": [
                "Architecture overview",
                "Component breakdown",
                "Data flow",
                "Technology decisions",
                "Risks and trade-offs",
                "Implementation sequence",
            ],
        },
        "build_ai_agent": {
            "title": "Build an AI Agent",
            "objective": (
                "Design and implement an AI agent around a concrete "
                "user problem."
            ),
            "process": [
                "Define the agent objective.",
                "Identify required inputs and outputs.",
                "Define tools and external capabilities.",
                "Define memory requirements.",
                "Design the agent workflow.",
                "Define evaluation criteria.",
                "Produce an implementation plan.",
            ],
            "output": [
                "Agent objective",
                "Architecture",
                "Tools",
                "Memory strategy",
                "Agent workflow",
                "Evaluation strategy",
                "Implementation plan",
            ],
        },
    },
    "learn": {
        "start_learning_path": {
            "title": "Start a Learning Path",
            "objective": (
                "Create a structured learning path for a technical topic."
            ),
            "process": [
                "Determine the user's current level.",
                "Define the target capability.",
                "Order concepts from foundational to advanced.",
                "Add practical exercises.",
                "Define checkpoints for progress.",
            ],
            "output": [
                "Learning objective",
                "Prerequisites",
                "Learning modules",
                "Practical exercises",
                "Milestones",
                "Next action",
            ],
        },
        "explore_concept": {
            "title": "Explore a Concept",
            "objective": (
                "Help the user understand a technical concept deeply "
                "and apply it."
            ),
            "process": [
                "Give the core definition.",
                "Explain how the concept works.",
                "Show the important components.",
                "Give a concrete example.",
                "Connect it to real engineering usage.",
                "Identify common mistakes.",
                "Provide a small practical exercise.",
            ],
            "output": [
                "Concept explanation",
                "How it works",
                "Example",
                "Engineering application",
                "Common mistakes",
                "Practice task",
            ],
        },
        "practice": {
            "title": "Practice with LATZ",
            "objective": (
                "Create an interactive technical practice session."
            ),
            "process": [
                "Determine the topic.",
                "Give a practical challenge.",
                "Allow the user to attempt it.",
                "Provide hints only when needed.",
                "Evaluate the attempt.",
                "Explain the improvement path.",
            ],
            "output": [
                "Challenge",
                "Constraints",
                "Expected outcome",
                "Hints",
                "Evaluation criteria",
            ],
        },
    },
    "research": {
        "start_research": {
            "title": "Start Research",
            "objective": (
                "Turn a research idea into a structured research direction."
            ),
            "process": [
                "Define the research problem.",
                "Formulate research questions.",
                "Define objectives.",
                "Identify relevant variables or concepts.",
                "Propose a methodology.",
                "Define evaluation criteria.",
            ],
            "output": [
                "Research problem",
                "Research questions",
                "Objectives",
                "Methodology",
                "Expected contribution",
                "Evaluation plan",
            ],
        },
        "review_literature": {
            "title": "Review Literature",
            "objective": (
                "Help analyze and organize literature around a research topic."
            ),
            "process": [
                "Define the literature review scope.",
                "Identify themes and concepts.",
                "Compare methodologies.",
                "Identify limitations.",
                "Identify research gaps.",
                "Connect findings to the user's research direction.",
            ],
            "output": [
                "Review scope",
                "Themes",
                "Methodology comparison",
                "Limitations",
                "Research gaps",
                "Research direction",
            ],
        },
        "design_experiment": {
            "title": "Design an Experiment",
            "objective": (
                "Design a reproducible experiment for a research question."
            ),
            "process": [
                "Define the hypothesis.",
                "Identify variables.",
                "Define the dataset or experimental input.",
                "Define the experimental procedure.",
                "Define baselines.",
                "Define evaluation metrics.",
                "Define reproducibility requirements.",
            ],
            "output": [
                "Hypothesis",
                "Variables",
                "Dataset or inputs",
                "Procedure",
                "Baselines",
                "Metrics",
                "Expected observations",
            ],
        },
    },
    "explore": {
        "explore_technology": {
            "title": "Explore a Technology",
            "objective": (
                "Investigate a technology and determine where it is useful."
            ),
            "process": [
                "Define what the technology does.",
                "Explain its core architecture.",
                "Identify common use cases.",
                "Identify strengths and limitations.",
                "Identify integration requirements.",
                "Suggest a small experiment.",
            ],
            "output": [
                "Technology overview",
                "Core architecture",
                "Use cases",
                "Strengths",
                "Limitations",
                "Experiment idea",
            ],
        },
        "compare_approaches": {
            "title": "Compare Approaches",
            "objective": (
                "Compare technical approaches using explicit criteria."
            ),
            "process": [
                "Identify the approaches.",
                "Identify decision criteria.",
                "Compare capabilities.",
                "Compare complexity and cost.",
                "Compare scalability and maintainability.",
                "Explain trade-offs.",
            ],
            "output": [
                "Decision criteria",
                "Comparison",
                "Trade-offs",
                "Use-case suitability",
                "Implementation considerations",
            ],
        },
        "discover_ideas": {
            "title": "Discover Ideas",
            "objective": (
                "Generate technically meaningful ideas that can be explored "
                "through experiments or prototypes."
            ),
            "process": [
                "Understand the user's domain.",
                "Generate multiple candidate ideas.",
                "Explain the underlying technical opportunity.",
                "Estimate implementation complexity.",
                "Identify risks.",
                "Select concrete next experiments.",
            ],
            "output": [
                "Candidate ideas",
                "Technical opportunity",
                "Complexity",
                "Risks",
                "Experiment suggestions",
            ],
        },
    },
    "solve": {
        "define_problem": {
            "title": "Define the Problem",
            "objective": (
                "Convert an unclear engineering issue into a precise problem."
            ),
            "process": [
                "Capture the observed issue.",
                "Separate symptoms from causes.",
                "Identify constraints.",
                "Identify expected behavior.",
                "Define measurable success criteria.",
            ],
            "output": [
                "Problem statement",
                "Observed symptoms",
                "Constraints",
                "Expected behavior",
                "Success criteria",
            ],
        },
        "break_into_steps": {
            "title": "Break Into Steps",
            "objective": (
                "Decompose an engineering problem into actionable tasks."
            ),
            "process": [
                "Identify the main objective.",
                "Break the problem into components.",
                "Identify dependencies.",
                "Order the work.",
                "Define verification for each step.",
            ],
            "output": [
                "Problem decomposition",
                "Dependencies",
                "Ordered tasks",
                "Verification criteria",
                "Next action",
            ],
        },
        "work_through_solution": {
            "title": "Work Through a Solution",
            "objective": (
                "Guide the user from diagnosis through implementation "
                "and verification."
            ),
            "process": [
                "Understand the current state.",
                "Identify the likely cause.",
                "Propose a solution.",
                "Implement the solution.",
                "Verify the result.",
                "Identify follow-up improvements.",
            ],
            "output": [
                "Diagnosis",
                "Solution",
                "Implementation steps",
                "Verification",
                "Follow-up improvements",
            ],
        },
    },
}


def get_workflow(
    engine: str | None,
    action: str | None,
) -> dict[str, Any] | None:
    if not engine or not action:
        return None

    engine_workflows = ENGINE_WORKFLOWS.get(
        engine,
        {},
    )

    return engine_workflows.get(action)


def build_execution_context(
    engine: str | None,
    action: str | None,
) -> str:
    workflow = get_workflow(
        engine=engine,
        action=action,
    )

    if workflow is None:
        return ""

    lines = [
        "ENGINE EXECUTION CONTRACT",
        f"Workflow: {workflow['title']}",
        f"Objective: {workflow['objective']}",
        "",
        "Execution process:",
    ]

    for index, step in enumerate(
        workflow["process"],
        start=1,
    ):
        lines.append(
            f"{index}. {step}"
        )

    lines.extend(
        [
            "",
            "Expected output:",
        ]
    )

    for item in workflow["output"]:
        lines.append(
            f"- {item}"
        )

    lines.extend(
        [
            "",
            "Do not blindly follow every step if the user's request "
            "does not require it.",
            "Use the contract to structure the work, not to produce "
            "unnecessary sections.",
        ]
    )

    return "\n".join(lines)