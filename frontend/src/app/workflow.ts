import { useSyncExternalStore } from "react";
import type { ConversationCategory } from "../shared/api/types";
import type { EngineeringModeId } from "../shared/config/engineeringModes";

/** A piece of work handed to LATZ Chat: the first message, and how the backend should treat it. */
export type WorkspaceWorkflow = {
    engine: EngineeringModeId | null;
    action: string;
    label: string;
    projectId?: number;
    /** Start a new conversation for this message instead of continuing the latest one. */
    fresh?: boolean;
    /** Category for a conversation created by this workflow. */
    category?: ConversationCategory;
};

type Pending = { id: number; workflow: WorkspaceWorkflow | null };

/*
 * The workflow waiting to be sent lives in memory, not in the URL or history state:
 * reloading /chat must never send the same first message twice.
 */
let pending: Pending = { id: 0, workflow: null };
const listeners = new Set<() => void>();

function emit() {
    listeners.forEach((listener) => listener());
}

/** Queues a workflow for the chat screen and returns the URL to navigate to. */
export function queueWorkflow(workflow: WorkspaceWorkflow): string {
    pending = { id: pending.id + 1, workflow };
    emit();

    return workflow.projectId !== undefined ? `/chat?project=${workflow.projectId}` : "/chat";
}

/** Called by chat once the queued workflow's first message has been sent. */
export function clearWorkflow(): void {
    if (pending.workflow) {
        pending = { id: pending.id, workflow: null };
        emit();
    }
}

export function usePendingWorkflow(): Pending {
    return useSyncExternalStore(
        (listener) => {
            listeners.add(listener);
            return () => {
                listeners.delete(listener);
            };
        },
        () => pending,
        () => pending,
    );
}
