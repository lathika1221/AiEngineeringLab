import { API_BASE, clearToken, getToken } from "./client";

export class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

type RequestOptions = {
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    body?: unknown;
    signal?: AbortSignal;
};

let unauthorizedHandler: (() => void) | null = null;

/** Registers what happens when the backend rejects the session token (the session provider signs out). */
export function onUnauthorized(handler: (() => void) | null): void {
    unauthorizedHandler = handler;
}

/** Call when a request made outside apiFetch (the streaming chat) gets a 401. */
export function reportUnauthorized(): void {
    clearToken();
    unauthorizedHandler?.();
}

async function readError(response: Response): Promise<string> {
    try {
        const data: unknown = await response.json();

        if (data && typeof data === "object" && "detail" in data && typeof data.detail === "string") {
            return data.detail;
        }
    } catch {
        // Not JSON: fall through to the generic message.
    }

    return `Request failed (${response.status}).`;
}

/** Authenticated JSON request to the LATZ backend. Throws ApiError for any non-2xx answer. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {};

    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }

    if (options.body !== undefined) {
        headers["Content-Type"] = "application/json";
    }

    let response: Response;

    try {
        response = await fetch(`${API_BASE}${path}`, {
            method: options.method ?? "GET",
            headers,
            body: options.body === undefined ? undefined : JSON.stringify(options.body),
            signal: options.signal,
        });
    } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
            throw error;
        }

        throw new ApiError(0, "Can't reach the LATZ server. Check that the backend is running.");
    }

    if (response.status === 401) {
        reportUnauthorized();
        throw new ApiError(401, "Your session has expired. Sign in again.");
    }

    if (!response.ok) {
        throw new ApiError(response.status, await readError(response));
    }

    if (response.status === 204) {
        return undefined as T;
    }

    return (await response.json()) as T;
}

export function errorMessage(error: unknown, fallback: string): string {
    return error instanceof ApiError ? error.message : fallback;
}
