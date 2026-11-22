import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

const root = new URL("..", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root), "utf8");

function inlineScripts(html: string): string[] {
    return [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
}

const hash = (body: string) => `'sha256-${createHash("sha256").update(body).digest("base64")}'`;

function policy(): Map<string, string> {
    const line = read("public/_headers")
        .split("\n")
        .find((l) => l.trim().startsWith("Content-Security-Policy-Report-Only:"));
    assert.ok(line, "report-only CSP header is missing from public/_headers");
    const directives = line.slice(line.indexOf(":") + 1).split(";").map((d) => d.trim()).filter(Boolean);
    return new Map(directives.map((d) => [d.split(/\s+/)[0], d.split(/\s+/).slice(1).join(" ")]));
}

test("every inline script in index.html is allowed by a hash in script-src", () => {
    const scripts = inlineScripts(read("index.html"));
    assert.ok(scripts.length > 0);
    const scriptSrc = policy().get("script-src") ?? "";
    for (const body of scripts) assert.ok(scriptSrc.includes(hash(body)), `script-src lacks ${hash(body)}`);
});

test("the built index.html (when present) has no inline script outside the hash list", () => {
    if (!existsSync(new URL("dist/index.html", root))) return;
    const scriptSrc = policy().get("script-src") ?? "";
    for (const body of inlineScripts(read("dist/index.html"))) assert.ok(scriptSrc.includes(hash(body)));
});

test("policy never allows unsafe script sources or wildcards", () => {
    const p = policy();
    assert.ok(!(p.get("script-src") ?? "").includes("unsafe"));
    assert.ok(!(p.get("script-src") ?? "").includes("*"));
    assert.equal(p.get("object-src"), "'none'");
    assert.equal(p.get("base-uri"), "'self'");
    assert.equal(p.get("frame-ancestors"), "'none'");
    for (const [name, value] of p) assert.ok(!/(^|\s)\*(\s|$)/.test(value), `${name} contains a bare wildcard`);
});

test("connect-src allows the API origin only, plus self", () => {
    const connect = (policy().get("connect-src") ?? "").split(/\s+/).sort();
    assert.deepEqual(connect, ["'self'", "https://ael-backend-production.up.railway.app"]);
});

test("external hosts are limited to the Google Fonts origins index.html actually uses", () => {
    const html = read("index.html");
    const used = new Set([...html.matchAll(/https:\/\/[a-z.]+(?=[/"])/g)].map((m) => m[0]));
    assert.ok(used.has("https://fonts.googleapis.com") && used.has("https://fonts.gstatic.com"));
    const p = policy();
    assert.ok((p.get("style-src") ?? "").includes("https://fonts.googleapis.com"));
    assert.ok((p.get("font-src") ?? "").includes("https://fonts.gstatic.com"));
});

test("no SPA catch-all in _redirects (Cloudflare ignores it and warns about a loop)", () => {
    assert.equal(existsSync(new URL("public/_redirects", root)), false);
});
