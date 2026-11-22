import type { ReactNode } from "react";
import { CircleAlert, Check } from "lucide-react";

type NoticeProps = {
    tone?: "error" | "success" | "info";
    children: ReactNode;
};

/** Inline message attached to the thing it describes. Errors are announced to assistive tech. */
export default function Notice({ tone = "info", children }: NoticeProps) {
    return (
        <div
            className={`notice${tone === "info" ? "" : ` notice--${tone}`}`}
            role={tone === "error" ? "alert" : "status"}
        >
            {tone === "success" ? <Check size={15} /> : <CircleAlert size={15} />}
            <span>{children}</span>
        </div>
    );
}
