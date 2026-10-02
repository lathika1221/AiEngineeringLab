import "./MissionControl.css";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import EngineeringCompass from "../../shared/components/EngineeringCompass";
import type { WorkspaceAction } from "../../app/layouts/WorkspaceLayout";

type MissionControlProps = {
    onAskLatz: () => void;
    workspaceAction: WorkspaceAction;
    onWorkspaceAction: (
        action: WorkspaceAction,
    ) => void;
};

type UserContext = {
    profile: {
        display_name: string | null;
        bio: string | null;
        timezone: string | null;
        onboarding_completed: string;
    } | null;
    life_roles: Array<{
        id: number;
        role: string;
        description: string | null;
        priority: number;
    }>;
    goals: Array<{
        id: number;
        title: string;
        description: string | null;
        category: string | null;
        priority: number;
        status: string;
        target_date: string | null;
    }>;
    memories: Array<{
        id: number;
        type: string;
        content: string;
    }>;
};

type MissionStat = {
    label: string;
    value: string;
    detail: string;
};

const quickActions: Array<{
    title: string;
    description: string;
    action: string;
    target: WorkspaceAction | "chat";
}> = [
        {
            title: "New Project",
            description:
                "Start building a new AI engineering project.",
            action: "Create",
            target: "forge",
        },
        {
            title: "New Experiment",
            description:
                "Run an experiment with models, prompts or data.",
            action: "Launch",
            target: "experiment",
        },
        {
            title: "Open Project",
            description:
                "Continue working on an existing engineering project.",
            action: "Open",
            target: "projects",
        },
        {
            title: "Ask LATZ",
            description:
                "Get help reasoning through an engineering problem.",
            action: "Chat",
            target: "chat",
        },
    ];

export default function MissionControl({
    onAskLatz,
    workspaceAction,
    onWorkspaceAction,
}: MissionControlProps) {
    const [context, setContext] =
        useState<UserContext | null>(null);

    const [loadingContext, setLoadingContext] =
        useState(true);

    const [contextError, setContextError] =
        useState(false);

    useEffect(() => {
        const accessToken =
            localStorage.getItem("access_token");

        if (!accessToken) {
            setLoadingContext(false);
            setContextError(true);
            return;
        }

        async function loadContext() {
            try {
                const response = await fetch(
                    "http://127.0.0.1:8000/users/context",
                    {
                        headers: {
                            Authorization: `Bearer ${accessToken}`,
                        },
                    },
                );

                if (!response.ok) {
                    throw new Error(
                        "Failed to load user context",
                    );
                }

                const data =
                    (await response.json()) as UserContext;

                setContext(data);
            } catch (error) {
                console.error(
                    "Mission Control context error:",
                    error,
                );

                setContextError(true);
            } finally {
                setLoadingContext(false);
            }
        }

        loadContext();
    }, []);

    const stats: MissionStat[] = [
        {
            label: "Life Roles",
            value: loadingContext
                ? "—"
                : String(
                    context?.life_roles?.length ?? 0,
                ),
            detail: "Active identities",
        },
        {
            label: "Active Goals",
            value: loadingContext
                ? "—"
                : String(
                    context?.goals?.filter(
                        (goal) =>
                            goal.status !==
                            "completed",
                    ).length ?? 0,
                ),
            detail: "Current objectives",
        },
        {
            label: "Memories",
            value: loadingContext
                ? "—"
                : String(
                    context?.memories?.length ?? 0,
                ),
            detail: "Saved context",
        },
    ];

    const actionTitle: Record<
        WorkspaceAction,
        string
    > = {
        forge: "Forge",
        learn: "Learn",
        research: "Research",
        explore: "Explore",
        solve: "Solve",
        projects: "Projects",
        experiment: "Experiment",
    };

    const actionDescription: Record<
        WorkspaceAction,
        string
    > = {
        forge:
            "Build software, APIs and AI agents.",
        learn:
            "Understand concepts and build new skills.",
        research:
            "Investigate problems, papers and experiments.",
        explore:
            "Explore ideas, technologies and possibilities.",
        solve:
            "Break down problems and engineer practical solutions.",
        projects:
            "Continue working on your engineering projects.",
        experiment:
            "Run experiments with models, prompts or data.",
    };

    function handleQuickAction(
        target: WorkspaceAction | "chat",
    ) {
        if (target === "chat") {
            onAskLatz();
            return;
        }

        onWorkspaceAction(target);
    }

    return (
        <motion.section
            className="mission-control"
            initial={{
                opacity: 0,
                y: 24,
            }}
            animate={{
                opacity: 1,
                y: 0,
            }}
            transition={{
                duration: 0.6,
            }}
        >
            <div className="mission-hero">
                <div className="mission-hero-copy">
                    <span className="mission-eyebrow">
                        AI ENGINEERING LAB
                    </span>

                    <h1>
                        Engineer.
                        <span>
                            {" "}
                            Experiment.{" "}
                        </span>
                        Evolve.
                    </h1>

                    <p>
                        A workspace for building
                        intelligent systems,
                        experimenting with AI, and
                        turning ideas into working
                        engineering projects.
                    </p>

                    <div className="mission-actions">
                        <button
                            className="primary-action"
                            onClick={() =>
                                onWorkspaceAction(
                                    "forge",
                                )
                            }
                        >
                            Start Building
                        </button>

                        <button
                            className="secondary-action"
                            onClick={() =>
                                onWorkspaceAction(
                                    "projects",
                                )
                            }
                        >
                            View Projects
                        </button>
                    </div>
                </div>

                <motion.div
                    className="mission-wolf"
                    animate={{
                        y: [0, -8, 0],
                    }}
                    transition={{
                        duration: 4,
                        repeat: Infinity,
                        ease: "easeInOut",
                    }}
                >
                    🐺
                </motion.div>
            </div>

            <div className="mission-stats">
                {stats.map((stat) => (
                    <div
                        className="stat-card"
                        key={stat.label}
                    >
                        <span>
                            {stat.label}
                        </span>

                        <strong>
                            {stat.value}
                        </strong>

                        <small>
                            {stat.detail}
                        </small>
                    </div>
                ))}
            </div>

            {contextError && (
                <div
                    className="mission-context-status"
                    role="status"
                >
                    LATZ couldn't load your latest
                    workspace context.
                </div>
            )}

            <div className="mission-section">
                <div className="section-heading">
                    <div>
                        <span>
                            ENGINEERING MODES
                        </span>

                        <h2>
                            What are we
                            engineering today?
                        </h2>
                    </div>

                    <p>
                        Choose a direction and let the
                        workspace adapt.
                    </p>
                </div>

                <div className="mission-mode-state">
                    <span>
                        CURRENT MODE
                    </span>

                    <strong>
                        {actionTitle[
                            workspaceAction
                        ]}
                    </strong>

                    <p>
                        {
                            actionDescription[
                            workspaceAction
                            ]
                        }
                    </p>
                </div>

                <EngineeringCompass
                    selectedMode={
                        workspaceAction
                    }
                    onSelectMode={
                        onWorkspaceAction
                    }
                />
            </div>

            <div className="mission-section">
                <div className="section-heading">
                    <div>
                        <span>
                            QUICK START
                        </span>

                        <h2>
                            Start with an
                            engineering path
                        </h2>
                    </div>
                </div>

                <div className="quick-grid">
                    {quickActions.map(
                        (action, index) => (
                            <motion.button
                                key={action.title}
                                className="quick-card"
                                onClick={() =>
                                    handleQuickAction(
                                        action.target,
                                    )
                                }
                                whileHover={{
                                    y: -5,
                                    scale: 1.01,
                                }}
                                whileTap={{
                                    scale: 0.98,
                                }}
                                transition={{
                                    duration: 0.2,
                                }}
                            >
                                <div className="quick-card-top">
                                    <span className="quick-number">
                                        0{index + 1}
                                    </span>

                                    <span className="quick-action">
                                        {
                                            action.action
                                        }
                                    </span>
                                </div>

                                <div className="quick-card-content">
                                    <h3>
                                        {
                                            action.title
                                        }
                                    </h3>

                                    <p>
                                        {
                                            action.description
                                        }
                                    </p>
                                </div>

                                <span className="quick-arrow">
                                    →
                                </span>
                            </motion.button>
                        ),
                    )}
                </div>
            </div>
        </motion.section>
    );
}