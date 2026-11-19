import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    block?: boolean;
    busy?: boolean;
    children: ReactNode;
};

export default function Button({
    variant = "secondary",
    size = "md",
    block = false,
    busy = false,
    className = "",
    type = "button",
    disabled,
    children,
    ...rest
}: ButtonProps) {
    const classes = [
        "btn",
        `btn--${variant}`,
        size !== "md" ? `btn--${size}` : "",
        block ? "btn--block" : "",
        className,
    ]
        .filter(Boolean)
        .join(" ");

    return (
        <button
            type={type}
            className={classes}
            disabled={disabled || busy}
            aria-busy={busy || undefined}
            {...rest}
        >
            {busy && <span className="spinner" aria-hidden="true" />}
            {children}
        </button>
    );
}
