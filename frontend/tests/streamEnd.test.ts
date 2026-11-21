import assert from "node:assert/strict";
import { test } from "node:test";

import { emptyReplyMessage, incompleteReason, splitStreamEnd } from "../src/shared/api/streamEnd.ts";

const M = "\x1eLATZ-STREAM-END:";

test("every known end marker is parsed, unknown ones become error", () => {
    for (const end of ["stop", "length", "incomplete", "timeout"]) {
        assert.deepEqual(splitStreamEnd(`hi${M}${end}`), { text: "hi", end });
    }
    assert.equal(splitStreamEnd(`${M}weird`).end, "error");
    assert.equal(splitStreamEnd("hi").end, null);
});

test("a marker split across chunks is never shown", () => {
    assert.equal(splitStreamEnd("hello\x1eLATZ-STR").text, "hello");
});

test("an empty reply explains the cause instead of a generic 'no reply'", () => {
    const messages = (["error", "timeout", "length", "incomplete", null] as const).map(emptyReplyMessage);
    assert.match(emptyReplyMessage("error"), /provider could not complete/i);
    assert.match(emptyReplyMessage("error"), /does not count against your daily limit/i);
    assert.match(emptyReplyMessage("timeout"), /too long/i);
    assert.match(emptyReplyMessage("length"), /output budget/i);
    assert.match(emptyReplyMessage(null), /connection/i);
    for (const m of messages) assert.ok(!/model returned no reply/i.test(m));
});

test("timeout has its own incomplete explanation", () => {
    assert.match(incompleteReason("timeout"), /too long/i);
});
