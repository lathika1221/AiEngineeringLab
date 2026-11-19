import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import WolfHead from "../brand/WolfHead";

type Props = {
    children: ReactNode;
    /** Where the boundary sits. "page" keeps the sidebar usable; "app" is the last resort. */
    scope?: "page" | "app";
};

type State = { failed: boolean };

/**
 * Catches a crash while rendering (or a lazy page that failed to download) and shows a
 * recoverable message instead of a blank screen. Remount it with a `key` to reset it on navigation.
 */
export default class ErrorBoundary extends Component<Props, State> {
    state: State = { failed: false };

    static getDerivedStateFromError(): State {
        return { failed: true };
    }

    componentDidCatch(error: Error, info: ErrorInfo): void {
        console.error("LATZ page crashed:", error, info.componentStack);
    }

    render() {
        if (!this.state.failed) {
            return this.props.children;
        }

        return (
            <div className="empty error-boundary" role="alert">
                <WolfHead size={64} mood="error" />
                <h1 className="error-boundary__title">Something went wrong</h1>
                <p>This page hit an unexpected error. Your data is safe. Reload to try again.</p>
                <div className="error-boundary__actions">
                    <button type="button" className="btn btn--primary" onClick={() => window.location.reload()}>
                        Reload
                    </button>
                    {this.props.scope !== "app" && (
                        <button type="button" className="btn btn--secondary" onClick={() => this.setState({ failed: false })}>
                            Try again
                        </button>
                    )}
                </div>
            </div>
        );
    }
}
