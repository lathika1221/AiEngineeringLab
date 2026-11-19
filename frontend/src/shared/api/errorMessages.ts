/**
 * User-facing messages for failed requests. Pure functions only (no React, no
 * import.meta), so they can be tested with `npm test` (Node's built-in runner).
 *
 * Rules:
 * - A server `detail` is shown only when it is a short plain string. Anything else
 *   (HTML from a proxy, stack traces, validation arrays) falls back to fixed text.
 * - 5xx answers are never echoed except the backend's own fixed 502 text for chat.
 */

export const NETWORK_MESSAGE = "Can't reach the LATZ server. Check your connection and try again.";
export const SERVER_UNAVAILABLE_MESSAGE = "The LATZ server is unavailable right now. Please try again in a moment.";
export const SESSION_EXPIRED_MESSAGE = "Your session has expired. Sign in again.";
export const INVALID_CREDENTIALS_MESSAGE = "Invalid username or password.";
export const LOGIN_RATE_LIMIT_MESSAGE = "Too many sign-in attempts. Please wait a moment and try again.";
export const LOGIN_FAILED_MESSAGE = "Sign in failed. Please try again.";
export const CHAT_RATE_LIMIT_MESSAGE = "You've reached a usage limit. Please try again later.";
export const CHAT_REQUEST_REJECTED_MESSAGE = "The request could not be completed. Please try again.";
export const CHAT_GENERIC_MESSAGE = "Something went wrong while generating the reply. Please try again.";
export const CHAT_SERVER_ERROR_MESSAGE = "Something went wrong on the LATZ server. Please try again.";

const MAX_DETAIL_LENGTH = 200;
const MAX_RETRY_AFTER_SECONDS = 2 * 24 * 60 * 60;

/** An error whose message is already safe and written for the user. */
export class UserFacingError extends Error {
    constructor(message: string) {
        super(message);
        this.name = "UserFacingError";
    }
}

/** The backend's `detail` when it is a short, plain string; otherwise null. */
export function safeDetail(body: unknown): string | null {
    if (!body || typeof body !== "object" || !("detail" in body) || typeof body.detail !== "string") {
        return null;
    }

    // eslint-disable-next-line no-control-regex
    const text = body.detail.replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();

    if (!text || text.length > MAX_DETAIL_LENGTH || /[<>]/.test(text)) {
        return null;
    }

    return text;
}

/** Reads `detail` from an error response without ever throwing. */
export async function readSafeDetail(response: Response): Promise<string | null> {
    try {
        return safeDetail(await response.json());
    } catch {
        return null;
    }
}

/** Retry-After as whole seconds (the form the backend sends), or null when absent or unusable. */
export function retryAfterSeconds(value: string | null | undefined): number | null {
    if (!value || !/^\d{1,9}$/.test(value.trim())) {
        return null;
    }

    const seconds = Number.parseInt(value.trim(), 10);

    return seconds >= 1 && seconds <= MAX_RETRY_AFTER_SECONDS ? seconds : null;
}

export function formatWait(seconds: number): string {
    const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? "" : "s"}`;

    if (seconds <= 90) {
        return plural(seconds, "second");
    }

    if (seconds < 3600) {
        return plural(Math.ceil(seconds / 60), "minute");
    }

    return plural(Math.ceil(seconds / 3600), "hour");
}

function withRetry(message: string, retryAfter: string | null | undefined): string {
    const seconds = retryAfterSeconds(retryAfter);

    return seconds === null ? message : `${message} You can try again in about ${formatWait(seconds)}.`;
}

/** Message for a failed /auth/login response. 401 (and other client errors) keep the generic credentials message. */
export function loginFailureMessage(status: number, detail: string | null, retryAfter?: string | null): string {
    if (status === 429) {
        return withRetry(detail ?? LOGIN_RATE_LIMIT_MESSAGE, retryAfter);
    }

    if (status >= 500) {
        return SERVER_UNAVAILABLE_MESSAGE;
    }

    return INVALID_CREDENTIALS_MESSAGE;
}

/** Message for a failed /ai/chat/stream response. A 401 is normally handled by the session code before this runs. */
export function chatFailureMessage(status: number, detail: string | null, retryAfter?: string | null): string {
    if (status === 401) {
        return SESSION_EXPIRED_MESSAGE;
    }

    if (status === 429) {
        return withRetry(detail ?? CHAT_RATE_LIMIT_MESSAGE, retryAfter);
    }

    if (status === 503) {
        // The backend's own 503 carries a fixed explanation (AI switched off). Without one the
        // 503 came from the hosting layer, so say the server is unavailable instead.
        return detail ?? SERVER_UNAVAILABLE_MESSAGE;
    }

    if (status === 502) {
        return detail ?? SERVER_UNAVAILABLE_MESSAGE;
    }

    if (status >= 500) {
        return CHAT_SERVER_ERROR_MESSAGE;
    }

    return detail ?? CHAT_REQUEST_REJECTED_MESSAGE;
}

/** Builds the error to throw for a non-OK chat response. */
export async function chatFailureFromResponse(response: Response): Promise<UserFacingError> {
    const detail = await readSafeDetail(response);

    return new UserFacingError(chatFailureMessage(response.status, detail, response.headers.get("Retry-After")));
}

/** Message shown in the conversation for any error that ended a chat request (never an abort). */
export function chatErrorMessage(error: unknown): string {
    if (error instanceof UserFacingError) {
        return error.message;
    }

    if (error instanceof TypeError) {
        return NETWORK_MESSAGE;
    }

    return CHAT_GENERIC_MESSAGE;
}
