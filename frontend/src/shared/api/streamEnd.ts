/**
 * The chat stream is plain text. The backend ends every stream with this marker
 * followed by "stop" | "length" | "error". A stream that closes without it was cut
 * off in transit, so it is never treated as complete.
 */
const STREAM_END_MARKER = "\x1eLATZ-STREAM-END:";

export type StreamEnd = "stop" | "length" | "error" | "incomplete" | "interrupted";

/** Splits streamed text into the visible reply and how the stream ended. */
export function splitStreamEnd(raw: string): { text: string; end: StreamEnd | null } {
    const at = raw.indexOf(STREAM_END_MARKER);

    if (at === -1) {
        // A marker may arrive split across chunks; never show a partial one.
        const control = raw.indexOf("\x1e");
        return { text: control === -1 ? raw : raw.slice(0, control), end: null };
    }

    const reason = raw.slice(at + STREAM_END_MARKER.length).trim();
    const end: StreamEnd = reason === "stop" || reason === "length" || reason === "incomplete" ? reason : "error";
    return { text: raw.slice(0, at), end };
}

/** Plain-language explanation for a stream that did not finish cleanly. */
export function incompleteReason(end: StreamEnd): string {
    if (end === "length") return "The model reached its output length limit, so the reply stops early.";
    if (end === "incomplete") return "The model ended the reply without confirming it finished.";
    if (end === "error") return "The model stopped before finishing the reply.";
    return "The connection ended before the reply finished.";
}
