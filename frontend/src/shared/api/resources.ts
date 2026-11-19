import { useCallback, useEffect, useSyncExternalStore } from "react";
import { ApiError, apiFetch } from "./http";

/**
 * A small shared cache for GET requests.
 *
 * Screens that need the same list (projects, conversations, goals, memories) read
 * it through useApiResource. The request is made once, shared by every screen that
 * asks, and kept while the user moves around, so returning to a page shows its data
 * immediately and refreshes it in the background.
 */

type Entry = {
    status: "idle" | "loading" | "ready" | "error";
    data: unknown;
    error: string | null;
    fetchedAt: number;
};

const IDLE: Entry = { status: "idle", data: undefined, error: null, fetchedAt: 0 };
const FRESH_FOR_MS = 20_000;

const entries = new Map<string, Entry>();
const inflight = new Map<string, Promise<void>>();
const listeners = new Set<() => void>();
let generation = 0;

function emit() {
    listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
    listeners.add(listener);
    return () => {
        listeners.delete(listener);
    };
}

function setEntry(path: string, entry: Entry) {
    entries.set(path, entry);
    emit();
}

/** Fetches a resource unless a fresh copy is already cached. `force` always refetches. */
export function loadResource(path: string, force = false): Promise<void> {
    const current = entries.get(path) ?? IDLE;
    const pending = inflight.get(path);

    if (pending) {
        return pending;
    }

    if (!force && current.status === "ready" && Date.now() - current.fetchedAt < FRESH_FOR_MS) {
        return Promise.resolve();
    }

    const startedIn = generation;

    if (current.status !== "ready") {
        setEntry(path, { ...current, status: "loading", error: null });
    }

    const request = apiFetch<unknown>(path)
        .then((data) => {
            if (startedIn === generation) {
                setEntry(path, { status: "ready", data, error: null, fetchedAt: Date.now() });
            }
        })
        .catch((error: unknown) => {
            if (startedIn !== generation) {
                return;
            }

            const message = error instanceof ApiError ? error.message : "Something went wrong.";
            const previous = entries.get(path) ?? IDLE;

            // Keep showing data we already have; only surface the error when there is none.
            setEntry(
                path,
                previous.data === undefined
                    ? { status: "error", data: undefined, error: message, fetchedAt: 0 }
                    : { ...previous, status: "ready", fetchedAt: 0 },
            );
        })
        .finally(() => {
            inflight.delete(path);
        });

    inflight.set(path, request);
    return request;
}

/** Replaces cached data in place after a successful create, update or delete. */
export function updateResource<T>(path: string, update: (current: T) => T): void {
    const current = entries.get(path);

    if (current && current.data !== undefined) {
        setEntry(path, { ...current, data: update(current.data as T) });
    }
}

/** Marks cached resources as stale and refetches the ones on screen. */
export function refreshResources(...paths: string[]): void {
    paths.forEach((path) => {
        if (entries.has(path)) {
            void loadResource(path, true);
        }
    });
}

/** Forgets everything. Called when the signed-in user changes. */
export function clearResources(): void {
    generation += 1;
    entries.clear();
    inflight.clear();
    emit();
}

export type Resource<T> = {
    data: T | undefined;
    /** True only while there is nothing to show yet. */
    loading: boolean;
    error: string | null;
    reload: () => void;
};

export function useApiResource<T>(path: string | null): Resource<T> {
    const entry = useSyncExternalStore(
        subscribe,
        () => (path ? (entries.get(path) ?? IDLE) : IDLE),
        () => IDLE,
    );

    useEffect(() => {
        if (path) {
            void loadResource(path);
        }
    }, [path]);

    const reload = useCallback(() => {
        if (path) {
            void loadResource(path, true);
        }
    }, [path]);

    return {
        data: entry.data as T | undefined,
        loading: path !== null && entry.data === undefined && entry.status !== "error",
        error: entry.status === "error" ? entry.error : null,
        reload,
    };
}
