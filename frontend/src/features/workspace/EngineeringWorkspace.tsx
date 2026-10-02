import "./EngineeringWorkspace.css";
import { motion } from "framer-motion";
import type { WorkspaceAction } from "../../app/layouts/WorkspaceLayout";

type EngineeringWorkspaceProps = {
    mode: WorkspaceAction;
    onBack: () => void;
    onAction: (action: string) => void;
};

const workspaceContent: Record<
    WorkspaceAction,
    {
        eyebrow: string;
        title: string;
        description: string;
        actions: string[];
    }
> = {
    forge: {
        eyebrow: "FORGE",
        title: "Build something real.",
        description:
            "Turn an idea into a working software system, API, AI agent, or engineering project.",
        actions: [
            "Create new project",
            "Design system architecture",
            "Build an AI agent",
        ],
    },

    learn: {
        eyebrow: "LEARN",
        title: "Understand. Practice. Master.",
        description:
            "Build technical understanding through structured learning, examples, experiments, and practice.",
        actions: [
            "Start a learning path",
            "Explore a concept",
            "Practice with LATZ",
        ],
    },

    research: {
        eyebrow: "RESEARCH",
        title: "Investigate the unknown.",
        description:
            "Explore research questions, literature, experiments, hypotheses, and technical evidence.",
        actions: [
            "Start research topic",
            "Review literature",
            "Design an experiment",
        ],
    },

    explore: {
        eyebrow: "EXPLORE",
        title: "Discover what is possible.",
        description:
            "Explore technologies, ideas, architectures, tools, and possibilities before committing to a direction.",
        actions: [
            "Explore a technology",
            "Compare approaches",
            "Discover ideas",
        ],
    },

    solve: {
        eyebrow: "SOLVE",
        title: "Break the problem down.",
        description:
            "Turn difficult engineering problems into smaller, testable and actionable steps.",
        actions: [
            "Define the problem",
            "Break it into steps",
            "Work through a solution",
        ],
    },

    projects: {
        eyebrow: "PROJECTS",
        title: "Your engineering projects.",
        description:
            "Continue building, reviewing, and organizing the projects in your workspace.",
        actions: [
            "Create new project",
            "Open existing project",
            "Review project progress",
        ],
    },

    experiment: {
        eyebrow: "EXPERIMENT",
        title: "Test an idea.",
        description:
            "Run controlled experiments with models, prompts, datasets, architectures, and engineering ideas.",
        actions: [
            "New model experiment",
            "Prompt experiment",
            "Dataset experiment",
        ],
    },
};

export default function EngineeringWorkspace({
    mode,
    onBack,
    onAction,
}: EngineeringWorkspaceProps) {
    const content = workspaceContent[mode];

    return (
        <motion.section
            className="engineering-workspace"
            initial={{
                opacity: 0,
                y: 20,
            }}
            animate={{
                opacity: 1,
                y: 0,
            }}
            transition={{
                duration: 0.35,
            }}
        >
            <button
                type="button"
                className="workspace-back"
                onClick={onBack}
            >
                ← Mission Control
            </button>

            <div className="engineering-workspace-header">
                <span>{content.eyebrow}</span>

                <h1>{content.title}</h1>

                <p>{content.description}</p>
            </div>

            <div className="engineering-workspace-grid">
                {content.actions.map((action, index) => (
                    <motion.button
                        type="button"
                        className="engineering-action-card"
                        key={action}
                        onClick={() => onAction(action)}
                        whileHover={{
                            y: -5,
                        }}
                        whileTap={{
                            scale: 0.98,
                        }}
                    >
                        <span>
                            0{index + 1}
                        </span>

                        <h3>{action}</h3>

                        <p>
                            Start working with LATZ on
                            this path.
                        </p>

                        <strong>→</strong>
                    </motion.button>
                ))}
            </div>
        </motion.section>
    );
}