import WolfHead from "./WolfHead";
import type { WolfMood } from "./WolfHead";
import "./Wordmark.css";

type WordmarkProps = {
    size?: "sm" | "md";
    /** Shows "AI Engineering Lab" under the name. */
    descriptor?: boolean;
    /** The wolf's state. The workspace shows `offline` while the backend is unreachable. */
    mood?: WolfMood;
};

/** Wolf head plus the LATZ name. The one lockup used across the product. */
export default function Wordmark({ size = "md", descriptor = false, mood = "idle" }: WordmarkProps) {
    return (
        <span className={`wordmark wordmark--${size}`}>
            <WolfHead size={size === "sm" ? 28 : 34} mood={mood} />
            <span className="wordmark__copy">
                <span className="wordmark__name">LATZ</span>{" "}
                {descriptor && <span className="wordmark__descriptor">AI Engineering Lab</span>}
            </span>
        </span>
    );
}
