import { NETWORK_MESSAGE, SERVER_UNAVAILABLE_MESSAGE, formatWait, retryAfterSeconds, safeDetail } from "../../shared/api/errorMessages.ts";
import { MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH, type RegistrationInput } from "./registerRules.ts";

export const REGISTER_FAILED_MESSAGE = "Unable to create your account. Check your details and try again.";
export const ACCOUNT_EXISTS_MESSAGE = "An account with that username or email already exists. Try signing in instead.";
export const REGISTRATION_RATE_LIMIT_MESSAGE = "Too many sign-up attempts. Please wait a moment and try again.";

export type RegisterResult = { ok: true } | { ok: false; message: string };

const FIELD_LABELS: Record<string, string> = { username: "Username", email: "Email", password: "Password" };
const MAX_ISSUES_SHOWN = 3;
const MAX_ISSUE_LENGTH = 160;

type Issue = { loc?: unknown; msg?: unknown; type?: unknown; ctx?: unknown };

function fieldOf(issue: Issue): string | null {
    if (!Array.isArray(issue.loc) || issue.loc.length === 0) {
        return null;
    }

    const last = issue.loc[issue.loc.length - 1];

    return typeof last === "string" && last in FIELD_LABELS ? last : null;
}

function cleanText(value: unknown): string | null {
    if (typeof value !== "string") {
        return null;
    }

    // eslint-disable-next-line no-control-regex
    const text = value.replace(/^Value error,\s*/i, "").replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();

    return text && text.length <= MAX_ISSUE_LENGTH && !/[<>]/.test(text) ? text : null;
}

function sentence(text: string): string {
    return /[.!?]$/.test(text) ? text : `${text}.`;
}

/** One user-facing sentence for one FastAPI validation issue. */
export function describeIssue(issue: Issue): string {
    const field = fieldOf(issue);
    const label = field ? FIELD_LABELS[field] : null;
    const ctx = issue.ctx && typeof issue.ctx === "object" ? (issue.ctx as Record<string, unknown>) : {};

    if (field === "password" && issue.type === "string_too_short") {
        const min = typeof ctx.min_length === "number" ? ctx.min_length : MIN_PASSWORD_LENGTH;

        return `Password must contain at least ${min} characters.`;
    }

    if (field === "email") {
        return "Enter a valid email address.";
    }

    const text = cleanText(issue.msg);

    if (field === "password" && text && /72/.test(text)) {
        return `Password is too long. Use at most ${MAX_PASSWORD_BYTES} bytes.`;
    }

    if (text && field === "username") {
        return sentence(text);
    }

    if (text && label) {
        return sentence(`${label}: ${text}`);
    }

    return label ? `Check the ${label.toLowerCase()} and try again.` : REGISTER_FAILED_MESSAGE;
}

/**
 * Message for a non-OK /auth/register response. FastAPI sends `detail` as a plain string for
 * rule rejections (400, 403, 429) and as a list of issues for validation (422). Server errors
 * and unreadable bodies never reach the user as text.
 */
export function registrationFailureMessage(status: number, body: unknown, retryAfter?: string | null): string {
    if (status >= 500) {
        return SERVER_UNAVAILABLE_MESSAGE;
    }

    const detail = safeDetail(body);

    if (status === 429) {
        const seconds = retryAfterSeconds(retryAfter);
        const base = detail ?? REGISTRATION_RATE_LIMIT_MESSAGE;

        return seconds === null ? base : `${base} You can try again in about ${formatWait(seconds)}.`;
    }

    if (status === 400 && detail && /already exists/i.test(detail)) {
        return ACCOUNT_EXISTS_MESSAGE;
    }

    if (status === 422 && body && typeof body === "object" && "detail" in body && Array.isArray(body.detail)) {
        const lines = [...new Set((body.detail as Issue[]).filter((i) => i && typeof i === "object").map(describeIssue))].slice(0, MAX_ISSUES_SHOWN);

        return lines.length > 0 ? lines.join(" ") : REGISTER_FAILED_MESSAGE;
    }

    return detail ?? REGISTER_FAILED_MESSAGE;
}

/** POST /auth/register. Never throws: every outcome is a result whose message is safe to show. */
export async function submitRegister(fetchFn: typeof fetch, apiBase: string, input: RegistrationInput): Promise<RegisterResult> {
    let response: Response;

    try {
        response = await fetchFn(`${apiBase}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: input.username.trim(), email: input.email.trim(), password: input.password }),
        });
    } catch (error) {
        return { ok: false, message: error instanceof TypeError ? NETWORK_MESSAGE : REGISTER_FAILED_MESSAGE };
    }

    if (response.ok) {
        return { ok: true };
    }

    let body: unknown = null;

    try {
        body = await response.json();
    } catch {
        // An unreadable body (HTML from a proxy, empty) falls back to fixed text below.
    }

    return { ok: false, message: registrationFailureMessage(response.status, body, response.headers.get("Retry-After")) };
}
