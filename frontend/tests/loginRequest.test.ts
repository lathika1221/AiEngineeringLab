import assert from "node:assert/strict";
import { test } from "node:test";

import { submitLogin } from "../src/features/auth/loginRequest.ts";
import {
    INVALID_CREDENTIALS_MESSAGE,
    LOGIN_FAILED_MESSAGE,
    NETWORK_MESSAGE,
    SERVER_UNAVAILABLE_MESSAGE,
} from "../src/shared/api/errorMessages.ts";

const BASE = "https://api.example.test";

function fakeFetch(respond: (url: string, init: RequestInit) => Response | Promise<Response>): typeof fetch {
    return ((url: string, init: RequestInit) => Promise.resolve(respond(url, init))) as unknown as typeof fetch;
}

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

test("success returns the token and posts the unchanged form request", async () => {
    let seen: { url: string; init: RequestInit } | null = null;
    const result = await submitLogin(
        fakeFetch((url, init) => {
            seen = { url, init };
            return json(200, { access_token: "tok-123", token_type: "bearer" });
        }),
        BASE,
        "latz",
        "pw",
    );

    assert.deepEqual(result, { ok: true, token: "tok-123" });
    assert.ok(seen);
    const { url, init } = seen as { url: string; init: RequestInit };
    assert.equal(url, `${BASE}/auth/login`);
    assert.equal(init.method, "POST");
    assert.deepEqual(init.headers, { "Content-Type": "application/x-www-form-urlencoded" });
    const body = init.body as URLSearchParams;
    assert.equal(body.get("grant_type"), "password");
    assert.equal(body.get("username"), "latz");
    assert.equal(body.get("password"), "pw");
});

test("401 keeps the generic invalid-credentials message and ignores the server text", async () => {
    const result = await submitLogin(fakeFetch(() => json(401, { detail: "Invalid username/email or password" })), BASE, "a", "b");
    assert.deepEqual(result, { ok: false, message: INVALID_CREDENTIALS_MESSAGE });
});

test("429 shows the server's rate-limit text and respects Retry-After", async () => {
    const result = await submitLogin(
        fakeFetch(() => json(429, { detail: "Too many requests. Please wait a moment and try again." }, { "Retry-After": "42" })),
        BASE,
        "a",
        "b",
    );
    assert.deepEqual(result, {
        ok: false,
        message: "Too many requests. Please wait a moment and try again. You can try again in about 42 seconds.",
    });
});

test("429 without a body or Retry-After falls back to fixed text", async () => {
    const result = await submitLogin(fakeFetch(() => new Response("<html>slow down</html>", { status: 429 })), BASE, "a", "b");
    assert.equal(result.ok, false);
    assert.match((result as { message: string }).message, /^Too many sign-in attempts\./);
    assert.doesNotMatch((result as { message: string }).message, /html|try again in about/i);
});

test("429 ignores an unusable Retry-After", async () => {
    for (const value of ["soon", "-5", "0", "Wed, 21 Oct 2026 07:28:00 GMT", "999999999"]) {
        const result = await submitLogin(fakeFetch(() => json(429, { detail: "Slow down." }, { "Retry-After": value })), BASE, "a", "b");
        assert.deepEqual(result, { ok: false, message: "Slow down." }, value);
    }
});

test("429 ignores an oversized or markup-bearing detail", async () => {
    for (const detail of ["x".repeat(500), "<script>alert(1)</script>"]) {
        const result = await submitLogin(fakeFetch(() => json(429, { detail })), BASE, "a", "b");
        assert.match((result as { message: string }).message, /^Too many sign-in attempts\./);
    }
});

test("5xx shows the generic server-unavailable message and never the body", async () => {
    for (const status of [500, 502, 503, 504]) {
        const result = await submitLogin(
            fakeFetch(() => json(status, { detail: "Traceback (most recent call last): secret internals" })),
            BASE,
            "a",
            "b",
        );
        assert.deepEqual(result, { ok: false, message: SERVER_UNAVAILABLE_MESSAGE }, String(status));
    }
});

test("network failure (fetch rejects with TypeError) gets its own message", async () => {
    const result = await submitLogin((() => Promise.reject(new TypeError("Failed to fetch"))) as unknown as typeof fetch, BASE, "a", "b");
    assert.deepEqual(result, { ok: false, message: NETWORK_MESSAGE });
});

test("an unexpected rejection does not leak its message", async () => {
    const result = await submitLogin((() => Promise.reject(new Error("internal detail"))) as unknown as typeof fetch, BASE, "a", "b");
    assert.deepEqual(result, { ok: false, message: LOGIN_FAILED_MESSAGE });
});

test("a 200 with an unreadable or token-less body is a failure, not a crash", async () => {
    for (const make of [() => new Response("not json", { status: 200 }), () => json(200, {}), () => json(200, { access_token: "" })]) {
        const result = await submitLogin(fakeFetch(make), BASE, "a", "b");
        assert.deepEqual(result, { ok: false, message: LOGIN_FAILED_MESSAGE });
    }
});
