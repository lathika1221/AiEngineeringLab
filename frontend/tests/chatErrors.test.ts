import assert from "node:assert/strict";
import { test } from "node:test";

import {
    CHAT_GENERIC_MESSAGE,
    CHAT_RATE_LIMIT_MESSAGE,
    CHAT_REQUEST_REJECTED_MESSAGE,
    CHAT_SERVER_ERROR_MESSAGE,
    NETWORK_MESSAGE,
    SERVER_UNAVAILABLE_MESSAGE,
    SESSION_EXPIRED_MESSAGE,
    UserFacingError,
    chatErrorMessage,
    chatFailureFromResponse,
    chatFailureMessage,
    formatWait,
    retryAfterSeconds,
    safeDetail,
} from "../src/shared/api/errorMessages.ts";

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

async function message(response: Response): Promise<string> {
    return (await chatFailureFromResponse(response)).message;
}

test("503 with the backend's AI-off detail says AI is unavailable and does not blame the backend", async () => {
    const text = await message(json(503, { detail: "AI features are temporarily unavailable." }));
    assert.equal(text, "AI features are temporarily unavailable.");
    assert.doesNotMatch(text, /backend is running|AEL/i);
});

test("503 from the hosting layer (no JSON) is a generic server-unavailable message", async () => {
    assert.equal(await message(new Response("<html>Service Unavailable</html>", { status: 503 })), SERVER_UNAVAILABLE_MESSAGE);
});

test("429 uses the server detail and Retry-After", async () => {
    const text = await message(
        json(429, { detail: "Daily AI request limit reached for your account." }, { "Retry-After": "7200" }),
    );
    assert.equal(text, "Daily AI request limit reached for your account. You can try again in about 2 hours.");
});

test("429 without detail falls back to a fixed usage-limit message", async () => {
    assert.equal(await message(new Response("", { status: 429 })), CHAT_RATE_LIMIT_MESSAGE);
    assert.equal(await message(json(429, { detail: [{ loc: ["x"] }] }, { "Retry-After": "30" })), `${CHAT_RATE_LIMIT_MESSAGE} You can try again in about 30 seconds.`);
});

test("401 maps to the session-expired message (the component signs out before this runs)", () => {
    assert.equal(chatFailureMessage(401, "anything", null), SESSION_EXPIRED_MESSAGE);
});

test("502 uses the backend's fixed provider message, otherwise generic", async () => {
    assert.equal(
        await message(json(502, { detail: "The AI provider could not complete the request. Please try again." })),
        "The AI provider could not complete the request. Please try again.",
    );
    assert.equal(await message(new Response("Bad Gateway", { status: 502 })), SERVER_UNAVAILABLE_MESSAGE);
});

test("other 5xx never echoes server text", async () => {
    for (const status of [500, 504, 599]) {
        assert.equal(await message(json(status, { detail: "Traceback: secret" })), CHAT_SERVER_ERROR_MESSAGE, String(status));
    }
});

test("other 4xx uses a safe detail or a fixed message", async () => {
    assert.equal(await message(json(404, { detail: "Conversation not found" })), "Conversation not found");
    assert.equal(await message(json(422, { detail: [{ msg: "bad" }] })), CHAT_REQUEST_REJECTED_MESSAGE);
});

test("chatErrorMessage: user-facing errors, network failures and everything else", () => {
    assert.equal(chatErrorMessage(new UserFacingError("Shown as is.")), "Shown as is.");
    assert.equal(chatErrorMessage(new TypeError("Failed to fetch")), NETWORK_MESSAGE);
    assert.equal(chatErrorMessage(new Error("boom: internal path /srv/app")), CHAT_GENERIC_MESSAGE);
    assert.equal(chatErrorMessage("string"), CHAT_GENERIC_MESSAGE);
});

test("the chat error text never mentions the old misleading wording", () => {
    for (const text of [SERVER_UNAVAILABLE_MESSAGE, NETWORK_MESSAGE, CHAT_GENERIC_MESSAGE, CHAT_SERVER_ERROR_MESSAGE]) {
        assert.doesNotMatch(text, /AEL|backend is running/);
    }
});

test("safeDetail accepts plain short strings only", () => {
    assert.equal(safeDetail({ detail: "  Too  many\n requests " }), "Too many requests");
    assert.equal(safeDetail({ detail: "a<b" }), null);
    assert.equal(safeDetail({ detail: "x".repeat(201) }), null);
    assert.equal(safeDetail({ detail: 5 }), null);
    assert.equal(safeDetail(null), null);
    assert.equal(safeDetail("detail"), null);
});

test("retryAfterSeconds and formatWait", () => {
    assert.equal(retryAfterSeconds("12"), 12);
    assert.equal(retryAfterSeconds(" 12 "), 12);
    for (const bad of [null, undefined, "", "0", "-1", "1.5", "abc", "999999999"]) assert.equal(retryAfterSeconds(bad), null, String(bad));
    assert.equal(formatWait(1), "1 second");
    assert.equal(formatWait(45), "45 seconds");
    assert.equal(formatWait(120), "2 minutes");
    assert.equal(formatWait(3601), "2 hours");
});
