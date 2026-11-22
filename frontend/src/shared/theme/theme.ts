import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "latz-theme";
const listeners = new Set<() => void>();

function readTheme(): Theme {
    return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function subscribe(listener: () => void) {
    listeners.add(listener);
    return () => {
        listeners.delete(listener);
    };
}

/** Applies the theme to the document and remembers it for the next visit. */
export function setTheme(theme: Theme): void {
    document.documentElement.dataset.theme = theme;

    try {
        localStorage.setItem(STORAGE_KEY, theme);
    } catch {
        // Storage can be unavailable (private mode); the theme still applies for this visit.
    }

    listeners.forEach((listener) => listener());
}

export function toggleTheme(): void {
    setTheme(readTheme() === "dark" ? "light" : "dark");
}

/** Current theme. The initial value is set before first paint by the script in index.html. */
export function useTheme(): Theme {
    return useSyncExternalStore(subscribe, readTheme, () => "dark");
}
