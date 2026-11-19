import { Hammer, GraduationCap, Microscope, Telescope, Puzzle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ConversationCategory } from "../api/types";

export type EngineeringModeId = "forge" | "learn" | "research" | "explore" | "solve";

export type ModeAction = {
    /** Sent to the backend as the chat request's `action`. */
    action: string;
    label: string;
    detail: string;
};

export type ModeTemplate = {
    name: string;
    detail: string;
    /** Starting text for the composer. Square brackets mark what to fill in. */
    prompt: string;
};

export type ModeTool = {
    label: string;
    detail: string;
    to: string;
};

export interface EngineeringMode {
    id: EngineeringModeId;
    title: string;
    /** One line, used in the compass and navigation. */
    description: string;
    icon: LucideIcon;
    headline: string;
    summary: string;
    /** Conversations started here are filed under this category. */
    category: ConversationCategory;
    placeholder: string;
    actions: ModeAction[];
    prompts: string[];
    templates: ModeTemplate[];
    tools: ModeTool[];
}

export const engineeringModes: EngineeringMode[] = [
    {
        id: "forge",
        title: "Forge",
        description: "Build software, APIs and AI agents.",
        icon: Hammer,
        headline: "Build something real",
        summary:
            "Turn an idea into a working software system, API, AI agent, or engineering project.",
        category: "projects",
        placeholder: "Describe what you want to build",
        actions: [
            {
                action: "create_project",
                label: "Create new project",
                detail: "Save a project so LATZ keeps its context",
            },
            {
                action: "design_architecture",
                label: "Design system architecture",
                detail: "Components, data flow and trade-offs",
            },
            {
                action: "build_ai_agent",
                label: "Build an AI agent",
                detail: "Tools, memory and the control loop",
            },
        ],
        prompts: [
            "Design a REST API for a task tracker with authentication",
            "Plan the folder structure for a FastAPI and React project",
            "Review my database schema and suggest improvements",
        ],
        templates: [
            {
                name: "Architecture brief",
                detail: "From requirements to a component plan",
                prompt:
                    "I'm building [what]. It needs to [main requirements]. Expected scale: [users / data]. Constraints: [stack, budget, deadline].\n\nPropose an architecture: components, data flow, the main trade-offs, and what to build first.",
            },
            {
                name: "Feature plan",
                detail: "Break one feature into steps",
                prompt:
                    "Feature: [describe it].\nCurrent stack: [stack].\n\nBreak this into implementation steps in order, with the files or modules each step touches and how to test it.",
            },
            {
                name: "Code review",
                detail: "Find problems before they ship",
                prompt:
                    "Review this code for bugs, unclear naming, missing error handling and performance problems. List the issues by severity, then show the corrected version.\n\n```\n[paste code]\n```",
            },
        ],
        tools: [
            { label: "Projects", detail: "Everything you've saved", to: "/projects" },
            { label: "Architecture explorer", detail: "Prototype a design in the lab", to: "/experiments" },
            { label: "Goals", detail: "What you're building toward", to: "/goals" },
        ],
    },
    {
        id: "learn",
        title: "Learn",
        description: "Master new technologies.",
        icon: GraduationCap,
        headline: "Understand, practise, master",
        summary:
            "Build technical understanding through structured learning, examples, experiments, and practice.",
        category: "learning",
        placeholder: "What do you want to learn?",
        actions: [
            {
                action: "start_learning_path",
                label: "Start a learning path",
                detail: "A sequence from basics to working knowledge",
            },
            {
                action: "explore_concept",
                label: "Explore a concept",
                detail: "One idea, explained with examples",
            },
            {
                action: "practice",
                label: "Practice with LATZ",
                detail: "Exercises with feedback on your answers",
            },
        ],
        prompts: [
            "Explain how transformers work, starting from attention",
            "Teach me Docker networking with a small example",
            "Quiz me on SQL joins and correct my answers",
        ],
        templates: [
            {
                name: "Learning path",
                detail: "A week-by-week plan",
                prompt:
                    "I want to learn [topic]. I already know [what you know]. I can spend [hours] a week for [weeks] weeks.\n\nBuild a learning path with a goal, resources and a small project for each week.",
            },
            {
                name: "Explain it three ways",
                detail: "Simple, technical, then by example",
                prompt:
                    "Explain [concept] three times: first in plain language, then precisely for an engineer, then with a worked example in [language].",
            },
            {
                name: "Practice set",
                detail: "Exercises that get harder",
                prompt:
                    "Give me five exercises on [topic], from easy to hard. Wait for my answer to each one before showing the solution.",
            },
        ],
        tools: [
            { label: "Goals", detail: "Track what you're learning", to: "/goals" },
            { label: "Memories", detail: "What LATZ knows about you", to: "/memories" },
            { label: "Prompt playground", detail: "Try an explanation style", to: "/experiments" },
        ],
    },
    {
        id: "research",
        title: "Research",
        description: "Analyze papers and datasets.",
        icon: Microscope,
        headline: "Investigate the unknown",
        summary:
            "Explore research questions, literature, experiments, hypotheses, and technical evidence.",
        category: "research",
        placeholder: "What question are you investigating?",
        actions: [
            {
                action: "start_research",
                label: "Start research topic",
                detail: "Scope the question and what's already known",
            },
            {
                action: "review_literature",
                label: "Review literature",
                detail: "Summarise and compare sources",
            },
            {
                action: "design_experiment",
                label: "Design an experiment",
                detail: "Hypothesis, method and what would disprove it",
            },
        ],
        prompts: [
            "Compare retrieval-augmented generation with fine-tuning",
            "What are the open problems in edge AI inference?",
            "Help me turn an observation into a testable hypothesis",
        ],
        templates: [
            {
                name: "Research question",
                detail: "Sharpen a vague idea",
                prompt:
                    "Topic: [topic].\nWhat I've noticed: [observation].\n\nTurn this into three precise research questions, say what evidence would answer each, and which is the most tractable.",
            },
            {
                name: "Paper summary",
                detail: "Structured notes on one paper",
                prompt:
                    "Summarise this paper: problem, method, key results, limitations, and what I could build on. Flag any claim the evidence doesn't fully support.\n\n[paste abstract or text]",
            },
            {
                name: "Experiment design",
                detail: "Method, controls and metrics",
                prompt:
                    "Hypothesis: [hypothesis].\nAvailable data or equipment: [resources].\n\nDesign an experiment: variables, controls, sample size, metrics, and the result that would prove me wrong.",
            },
        ],
        tools: [
            { label: "Research sandbox", detail: "Run a question in the lab", to: "/experiments" },
            { label: "Memories", detail: "Facts LATZ keeps for you", to: "/memories" },
            { label: "Projects", detail: "Attach findings to your work", to: "/projects" },
        ],
    },
    {
        id: "explore",
        title: "Explore",
        description: "Discover new tools and ideas.",
        icon: Telescope,
        headline: "Discover what is possible",
        summary:
            "Explore technologies, ideas, architectures, tools, and possibilities before committing to a direction.",
        category: "general",
        placeholder: "What are you curious about?",
        actions: [
            {
                action: "explore_technology",
                label: "Explore a technology",
                detail: "What it is, where it fits, where it doesn't",
            },
            {
                action: "compare_approaches",
                label: "Compare approaches",
                detail: "Options side by side with trade-offs",
            },
            {
                action: "discover_ideas",
                label: "Discover ideas",
                detail: "Directions you haven't considered yet",
            },
        ],
        prompts: [
            "Compare PostgreSQL, MongoDB and SQLite for a small product",
            "What can I build with a Raspberry Pi and a camera?",
            "Which vector databases are worth evaluating, and why?",
        ],
        templates: [
            {
                name: "Technology comparison",
                detail: "A table you can decide from",
                prompt:
                    "Compare [option A], [option B] and [option C] for [use case]. Use a table covering cost, learning curve, performance, ecosystem and risks, then recommend one.",
            },
            {
                name: "Idea generator",
                detail: "Projects that fit your constraints",
                prompt:
                    "I have [skills / hardware / time]. I'm interested in [areas].\n\nSuggest five project ideas, each with what makes it interesting, the hardest part, and a first step I can finish this week.",
            },
            {
                name: "Should I adopt it?",
                detail: "A decision check for one tool",
                prompt:
                    "I'm considering [tool or technology] for [project]. Give me the case for, the case against, what it replaces, and the signs that I should wait.",
            },
        ],
        tools: [
            { label: "Prompt playground", detail: "Compare two approaches quickly", to: "/experiments" },
            { label: "LATZ Chat", detail: "Open-ended conversation", to: "/chat" },
            { label: "Projects", detail: "Turn an idea into a project", to: "/projects" },
        ],
    },
    {
        id: "solve",
        title: "Solve",
        description: "Debug and solve engineering problems.",
        icon: Puzzle,
        headline: "Break the problem down",
        summary:
            "Turn difficult engineering problems into smaller, testable and actionable steps.",
        category: "general",
        placeholder: "Describe the problem or paste the error",
        actions: [
            {
                action: "define_problem",
                label: "Define the problem",
                detail: "State it precisely before fixing it",
            },
            {
                action: "break_into_steps",
                label: "Break it into steps",
                detail: "Smaller pieces you can test one at a time",
            },
            {
                action: "work_through_solution",
                label: "Work through a solution",
                detail: "Reason step by step to an answer",
            },
        ],
        prompts: [
            "My API returns 500 only under load. Where do I start?",
            "Help me find why this React component re-renders so often",
            "Walk me through debugging a failing Docker build",
        ],
        templates: [
            {
                name: "Bug report",
                detail: "Everything LATZ needs to diagnose",
                prompt:
                    "Expected: [what should happen].\nActual: [what happens].\nSteps to reproduce: [steps].\nEnvironment: [OS, versions].\n\nError:\n```\n[paste error or logs]\n```\n\nList the most likely causes in order and how to confirm each.",
            },
            {
                name: "Root cause analysis",
                detail: "From symptom to cause",
                prompt:
                    "Symptom: [describe].\nWhat changed recently: [changes].\nWhat I've ruled out: [list].\n\nWork backwards to the root cause. Ask me for the one piece of information that would narrow it most.",
            },
            {
                name: "Decision under constraints",
                detail: "Pick between imperfect options",
                prompt:
                    "Problem: [describe].\nOptions I see: [options].\nConstraints: [time, cost, risk].\n\nEvaluate each option against the constraints and recommend one, with the main risk and how to reduce it.",
            },
        ],
        tools: [
            { label: "LATZ Chat", detail: "Keep working the problem", to: "/chat" },
            { label: "Goals", detail: "Record what done looks like", to: "/goals" },
            { label: "Experiments", detail: "Test a fix in isolation", to: "/experiments" },
        ],
    },
];

export function findMode(id: string | null | undefined): EngineeringMode | undefined {
    return engineeringModes.find((mode) => mode.id === id);
}
