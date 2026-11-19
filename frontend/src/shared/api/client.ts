/**
 * Single source for the backend location and the stored session token.
 * Set VITE_API_URL to point the frontend at another backend. The localhost
 * default exists for local development only: a production bundle without
 * VITE_API_URL refuses to start (and `vite build` fails earlier, see
 * vite.config.ts) instead of silently calling the visitor's own machine.
 */
const configuredUrl: unknown = import.meta.env.VITE_API_URL;
const trimmedUrl = typeof configuredUrl === "string" ? configuredUrl.trim() : "";

if (!trimmedUrl && import.meta.env.PROD) {
    throw new Error("VITE_API_URL was not set when this production build was created.");
}

export const API_BASE = trimmedUrl ? trimmedUrl.replace(/\/+$/, "") : "http://127.0.0.1:8000";

const TOKEN_KEY = "access_token";

export function getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
    localStorage.removeItem(TOKEN_KEY);
}
