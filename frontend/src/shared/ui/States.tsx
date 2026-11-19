import type { ReactNode } from "react";
import Button from "./Button";

/** Placeholder rows shown while a list loads. Sized like the content that replaces them. */
export function SkeletonList({ rows = 3, height = 60 }: { rows?: number; height?: number }) {
    return (
        <div className="skeleton-list" role="status" aria-label="Loading">
            {Array.from({ length: rows }, (_, index) => (
                <div className="skeleton" key={index} style={{ height }} />
            ))}
        </div>
    );
}

export function SkeletonGrid({ cards = 3, height = 190 }: { cards?: number; height?: number }) {
    return (
        <div className="card-grid" role="status" aria-label="Loading">
            {Array.from({ length: cards }, (_, index) => (
                <div className="skeleton" key={index} style={{ height }} />
            ))}
        </div>
    );
}

type EmptyStateProps = {
    title: string;
    children?: ReactNode;
    action?: ReactNode;
};

/** Shown when a list has nothing in it yet. Says what goes here and how to add it. */
export function EmptyState({ title, children, action }: EmptyStateProps) {
    return (
        <div className="empty">
            <h3>{title}</h3>
            {children && <p>{children}</p>}
            {action}
        </div>
    );
}

/** Shown when a list failed to load. Always offers a retry. */
export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
    return (
        <div className="empty empty--error" role="alert">
            <h3>Couldn't load this</h3>
            <p>{message}</p>
            <Button size="sm" onClick={onRetry}>
                Try again
            </Button>
        </div>
    );
}
