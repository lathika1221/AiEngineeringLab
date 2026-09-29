import "./MissionControl.css";
import { motion } from "framer-motion";
import EngineeringCompass from "../../shared/components/EngineeringCompass";

export default function MissionControl() {
    return (

        <motion.div
            className="mission-control"
            initial={{
                opacity: 0,
                y: 30,
            }}
            animate={{
                opacity: 1,
                y: 0,
            }}
            transition={{
                duration: 0.8,
            }}
        >

            <motion.div
                className="wolf"
                animate={{
                    scale: [1, 1.03, 1],
                }}
                transition={{
                    duration: 4,
                    repeat: Infinity,
                    ease: "easeInOut",
                }}
            >
                🐺
            </motion.div>

            <h1>LATZ</h1>

            <p className="status">
                Ready when you are.
            </p>

            <p className="subtitle">
                What shall we engineer today?
            </p>

            <EngineeringCompass />

        </motion.div>

    );
}