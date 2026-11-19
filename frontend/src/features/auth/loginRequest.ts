import {
    LOGIN_FAILED_MESSAGE,
    NETWORK_MESSAGE,
    loginFailureMessage,
    readSafeDetail,
} from "../../shared/api/errorMessages.ts";

export type LoginResult = { ok: true; token: string } | { ok: false; message: string };

/**
 * POST /auth/login. Never throws: every outcome is a result whose message is safe to show.
 * `fetchFn` is injected so the behaviour can be tested without a browser.
 */
export async function submitLogin(
    fetchFn: typeof fetch,
    apiBase: string,
    username: string,
    password: string,
): Promise<LoginResult> {
    const formData = new URLSearchParams();

    formData.append("grant_type", "password");
    formData.append("username", username);
    formData.append("password", password);

    let response: Response;

    try {
        response = await fetchFn(`${apiBase}/auth/login`, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: formData,
        });
    } catch (error) {
        return { ok: false, message: error instanceof TypeError ? NETWORK_MESSAGE : LOGIN_FAILED_MESSAGE };
    }

    if (!response.ok) {
        const detail = response.status === 429 ? await readSafeDetail(response) : null;

        return {
            ok: false,
            message: loginFailureMessage(response.status, detail, response.headers.get("Retry-After")),
        };
    }

    try {
        const data: unknown = await response.json();
        const token = data && typeof data === "object" && "access_token" in data ? data.access_token : null;

        if (typeof token === "string" && token) {
            return { ok: true, token };
        }
    } catch {
        // Fall through: a success status with an unreadable body is not a usable sign-in.
    }

    return { ok: false, message: LOGIN_FAILED_MESSAGE };
}
