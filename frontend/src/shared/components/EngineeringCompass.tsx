import "./EngineeringCompass.css";
import { motion } from "framer-motion";
import { useState } from "react";
import { engineeringModes } from "../config/engineeringModes";

export default function EngineeringCompass() {
    const [selected, setSelected] = useState(engineeringModes[0]);

    return (
        <>
            <div className="description">
                <h3>{selected.title}</h3>
                <p>{selected.description}</p>
            </div>

            <div className="compass">
                {engineeringModes.map((mode) => (
                    <motion.button
                        key={mode.id}
                        className={`mode-node ${mode.id}`}
                        onMouseEnter={() => setSelected(mode)}
                        whileHover={{
                            scale: 1.08,
                            boxShadow: "0 0 30px rgba(56,189,248,.45)",
                        }}
                        whileTap={{
                            scale: 0.96,
                        }}
                    >
                        {mode.title}
                    </motion.button>
                ))}
            </div>
        </>
    );
}