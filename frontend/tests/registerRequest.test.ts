import assert from "node:assert/strict";
import test from "node:test";

import { NETWORK_MESSAGE, SERVER_UNAVAILABLE_MESSAGE } from "../src/shared/api/errorMessages.ts";
import {
    ACCOUNT_EXISTS_MESSAGE,
    REGISTER_FAILED_MESSAGE,
    registrationFailureMessage,
    submitRegister,
} from "../src/features/auth/registerRequest.ts";
import { MIN_PASSWORD_LENGTH, validateRegistration } from "../src/features/auth/registerRules.ts";

const base = { username: "lathika", email: "person@example.com", password: "x".repeat(12) };

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

test("minimum password length is 12", () => {
    assert.equal(MIN_PASSWORD_LENGTH, 12);
});

test("passwords of 8 to 11 characters are rejected by the client", () => {
    for (let length = 8; length <= 11; length += 1) {
        assert.equal(
            validateRegistration({ ...base, password: "p".repeat(length) }),
            "Password must contain at least 12 characters.",
            `length ${length}`,
        );
    }
});

test("passwords of 12 or more characters pass client validation", () => {
    for (const length of [12, 13, 40, 72]) {
        assert.equal(validateRegistration({ ...base, password: "p".repeat(length) }), null, `length ${length}`);
    }
});

test("password over 72 bytes is rejected", () => {
    assert.match(validateRegistration({ ...base, password: "p".repeat(73) }) ?? "", /too long/i);
});

test("username and email rules mirror the backend", () => {
    assert.match(validateRegistration({ ...base, username: "ab" }) ?? "", /3 to 100/);
    assert.match(validateRegistration({ ...base, username: "a@b.co" }) ?? "", /@/);
    assert.match(validateRegistration({ ...base, username: "two words" }) ?? "", /spaces/);
    assert.equal(validateRegistration({ ...base, email: "nope" }), "Enter a valid email address.");
    assert.equal(validateRegistration({ ...base, email: "UPPER@EXAMPLE.COM" }), null);
});

test("422 with a detail array becomes field-specific messages", () => {
    const body = {
        detail: [
            { type: "string_too_short", loc: ["body", "password"], msg: "String should have at least 12 characters", ctx: { min_length: 12 } },
            { type: "value_error", loc: ["body", "email"], msg: "value is not a valid email address: bad" },
        ],
    };

    assert.equal(registrationFailureMessage(422, body), "Password must contain at least 12 characters. Enter a valid email address.");
});

test("username validation message loses the pydantic prefix", () => {
    const body = { detail: [{ type: "value_error", loc: ["body", "username"], msg: "Value error, Username must not contain '@'" }] };

    assert.equal(registrationFailureMessage(422, body), "Username must not contain '@'.");
});

test("422 array never leaks input values or internals", () => {
    const body = { detail: [{ type: "x", loc: ["body", "password"], msg: "boom", input: "hunter2hunter2", url: "https://errors.pydantic.dev" }] };
    const message = registrationFailureMessage(422, body);

    assert.ok(!message.includes("hunter2"));
    assert.ok(!message.includes("pydantic"));
});

test("unknown or empty issue lists fall back to the generic message", () => {
    assert.equal(registrationFailureMessage(422, { detail: [] }), REGISTER_FAILED_MESSAGE);
    assert.equal(registrationFailureMessage(422, { detail: [{ loc: ["body", "other"], msg: "<script>" }] }), REGISTER_FAILED_MESSAGE);
});

test("duplicate account maps to the friendly message", () => {
    assert.equal(registrationFailureMessage(400, { detail: "Username or email already exists" }), ACCOUNT_EXISTS_MESSAGE);
});

test("string detail from 403 is shown", () => {
    assert.equal(registrationFailureMessage(403, { detail: "Registration is currently closed." }), "Registration is currently closed.");
});

test("429 includes the wait from Retry-After", () => {
    assert.match(registrationFailureMessage(429, { detail: "Too many requests" }, "30"), /Too many requests.*try again/);
});

test("5xx and non-JSON bodies never expose server details", () => {
    assert.equal(registrationFailureMessage(500, { detail: "Traceback (most recent call last)..." }), SERVER_UNAVAILABLE_MESSAGE);
    assert.equal(registrationFailureMessage(502, null), SERVER_UNAVAILABLE_MESSAGE);
    assert.equal(registrationFailureMessage(400, null), REGISTER_FAILED_MESSAGE);
});

test("submitRegister posts trimmed fields and reports success", async () => {
    let seen: { url: string; init?: RequestInit } | null = null;
    const fetchFn = (async (url: string, init?: RequestInit) => {
        seen = { url, init };
        return jsonResponse(200, { id: 1 });
    }) as unknown as typeof fetch;

    const result = await submitRegister(fetchFn, "https://api.test", { username: " user1 ", email: " A@B.co ", password: "p".repeat(12) });

    assert.deepEqual(result, { ok: true });
    assert.equal(seen!.url, "https://api.test/auth/register");
    assert.deepEqual(JSON.parse(String(seen!.init!.body)), { username: "user1", email: "A@B.co", password: "p".repeat(12) });
});

test("submitRegister turns a 422 array into a message, not an exception", async () => {
    const fetchFn = (async () =>
        jsonResponse(422, { detail: [{ type: "string_too_short", loc: ["body", "password"], msg: "short", ctx: { min_length: 12 } }] })) as unknown as typeof fetch;

    assert.deepEqual(await submitRegister(fetchFn, "", base), { ok: false, message: "Password must contain at least 12 characters." });
});

test("submitRegister handles an HTML error body and a network failure", async () => {
    const html = (async () => new Response("<html>Bad gateway</html>", { status: 502 })) as unknown as typeof fetch;
    const down = (async () => {
        throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    assert.deepEqual(await submitRegister(html, "", base), { ok: false, message: SERVER_UNAVAILABLE_MESSAGE });
    assert.deepEqual(await submitRegister(down, "", base), { ok: false, message: NETWORK_MESSAGE });
});
