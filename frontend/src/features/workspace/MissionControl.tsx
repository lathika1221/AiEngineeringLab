import "./MissionControl.css";
import { motion } from "framer-motion";
import EngineeringCompass from "../../shared/components/EngineeringCompass";

type MissionControlProps = {
    onAskLatz: () => void;
};

const stats = [
    {
        label: "AI Systems",
        value: "04",
        detail: "Active workspaces",
    },
    {
        label: "Experiments",
        value: "12",
        detail: "Running experiments",
    },
    {
        label: "Projects",
        value: "05",
        detail: "Engineering projects",
    },
];

const quickActions = [
    {
        title: "New Project",
        description:
            "Start building a new AI engineering project.",
        action: "Create",
    },
    {
        title: "New Experiment",
        description:
            "Run an experiment with models, prompts or data.",
        action: "Launch",
    },
    {
        title: "Open Project",
        description:
            "Continue working on an existing engineering project.",
        action: "Open",
    },
    {
        title: "Ask LATZ",
        description:
            "Get help reasoning through an engineering problem.",
        action: "Chat",
    },
];

export default function MissionControl({
    onAskLatz,
}: MissionControlProps) {
    return (
        <motion.section
            className="mission-control"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
        >
            <div className="mission-hero">
                <div className="mission-hero-copy">
                    <span className="mission-eyebrow">
                        AI ENGINEERING LAB
                    </span>

                    <h1>
                        Engineer.
                        <span> Experiment. </span>
                        Evolve.
                    </h1>

                    <p>
                        A workspace for building intelligent
                        systems, experimenting with AI, and
                        turning ideas into working engineering
                        projects.
                    </p>

                    <div className="mission-actions">
                        <button className="primary-action">
                            Start Building
                        </button>

                        <button className="secondary-action">
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
                        <span>{stat.label}</span>
                        <strong>{stat.value}</strong>
                        <small>{stat.detail}</small>
                    </div>
                ))}
            </div>

            <div className="mission-section">
                <div className="section-heading">
                    <div>
                        <span>ENGINEERING MODES</span>

                        <h2>
                            What are we engineering today?
                        </h2>
                    </div>

                    <p>
                        Choose a direction and let the
                        workspace adapt.
                    </p>
                </div>

                <EngineeringCompass />
            </div>

            <div className="mission-section">
                <div className="section-heading">
                    <div>
                        <span>QUICK START</span>

                        <h2>
                            Start with an engineering path
                        </h2>
                    </div>
                </div>

                <div className="quick-grid">
                    {quickActions.map((action, index) => (
                        <motion.button
                            key={action.title}
                            className="quick-card"
                            onClick={() => {
                                if (
                                    action.title ===
                                    "Ask LATZ"
                                ) {
                                    onAskLatz();
                                }
                            }}
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
                                    {action.action}
                                </span>
                            </div>

                            <div className="quick-card-content">
                                <h3>{action.title}</h3>

                                <p>
                                    {action.description}
                                </p>
                            </div>

                            <span className="quick-arrow">
                                →
                            </span>
                        </motion.button>
                    ))}
                </div>
            </div>
        </motion.section>
    );
}