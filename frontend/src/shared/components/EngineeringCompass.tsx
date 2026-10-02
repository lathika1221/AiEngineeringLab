import "./EngineeringCompass.css";
import { motion } from "framer-motion";
import { engineeringModes } from "../config/engineeringModes";
import type { WorkspaceAction } from "../../app/layouts/WorkspaceLayout";

type EngineeringCompassProps = {
    selectedMode: WorkspaceAction;
    onSelectMode: (
        mode: WorkspaceAction,
    ) => void;
};

const modeMap: Record<
    string,
    WorkspaceAction
> = {
    forge: "forge",
    learn: "learn",
    research: "research",
    explore: "explore",
    solve: "solve",
};

export default function EngineeringCompass({
    selectedMode,
    onSelectMode,
}: EngineeringCompassProps) {
    const selected =
        engineeringModes.find(
            (mode) =>
                modeMap[mode.id] ===
                selectedMode,
        ) ??
        engineeringModes[0];

    return (
        <>
            <div className="description">
                <h3>
                    {selected.title}
                </h3>

                <p>
                    {selected.description}
                </p>
            </div>

            <div className="compass">
                {engineeringModes.map(
                    (mode) => {
                        const workspaceMode =
                            modeMap[mode.id];

                        const isSelected =
                            workspaceMode ===
                            selectedMode;

                        return (
                            <motion.button
                                key={mode.id}
                                type="button"
                                className={`mode-node ${mode.id} ${isSelected
                                    ? "active"
                                    : ""
                                    }`}
                                onClick={() =>
                                    onSelectMode(
                                        workspaceMode,
                                    )
                                }
                                whileHover={{
                                    scale: 1.08,
                                    boxShadow:
                                        "0 0 30px rgba(56,189,248,.45)",
                                }}
                                whileTap={{
                                    scale: 0.96,
                                }}
                            >
                                {mode.title}
                            </motion.button>
                        );
                    },
                )}
            </div>
        </>
    );
}