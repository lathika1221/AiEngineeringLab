/**
 * A small syntax highlighter for chat code blocks.
 *
 * It recognises comments, strings, numbers, keywords, variables and call names
 * for the languages LATZ answers in most. It is deliberately not a full parser:
 * it adds no dependency and stays fast while a reply is streaming. Unknown
 * languages still get comments, strings and numbers.
 */

export type TokenKind = "comment" | "string" | "number" | "keyword" | "variable" | "function" | "property";

export type Token = { text: string; kind?: TokenKind };

type Family = "c" | "hash" | "shell" | "powershell" | "sql" | "markup" | "json" | "plain";

const ALIASES: Record<string, string> = {
    js: "javascript",
    jsx: "javascript",
    mjs: "javascript",
    ts: "typescript",
    tsx: "typescript",
    py: "python",
    sh: "bash",
    shell: "bash",
    zsh: "bash",
    console: "bash",
    ps: "powershell",
    ps1: "powershell",
    pwsh: "powershell",
    yml: "yaml",
    "c++": "cpp",
    cs: "csharp",
    rs: "rust",
    golang: "go",
    htm: "html",
    xml: "html",
    svg: "html",
    jsonc: "json",
    postgres: "sql",
    postgresql: "sql",
    mysql: "sql",
    dockerfile: "docker",
};

const FAMILY: Record<string, Family> = {
    javascript: "c",
    typescript: "c",
    java: "c",
    c: "c",
    cpp: "c",
    csharp: "c",
    go: "c",
    rust: "c",
    kotlin: "c",
    swift: "c",
    php: "c",
    dart: "c",
    css: "c",
    scss: "c",
    python: "hash",
    ruby: "hash",
    yaml: "hash",
    toml: "hash",
    docker: "hash",
    r: "hash",
    bash: "shell",
    powershell: "powershell",
    sql: "sql",
    html: "markup",
    json: "json",
};

function words(list: string): Set<string> {
    return new Set(list.split(" "));
}

const KEYWORDS: Record<Family, Set<string>> = {
    c: words(
        "abstract as async await break case catch class const continue default delete do else enum export extends " +
            "false final finally fn for from func function go if impl implements import in instanceof interface let " +
            "match mut namespace new null nil of package private protected pub public return static struct super " +
            "switch this throw true try type typeof undefined use using var void while yield int string bool float " +
            "double char long number boolean any never unknown readonly defer chan map range select self trait where",
    ),
    hash: words(
        "and as assert async await break class continue def del elif else except False finally for from global if " +
            "import in is lambda None nonlocal not or pass raise return True try while with yield self begin end do " +
            "module require then unless until when FROM RUN CMD COPY ADD ENV EXPOSE WORKDIR ENTRYPOINT ARG USER " +
            "VOLUME LABEL true false null",
    ),
    shell: words(
        "if then else elif fi for while until do done case esac in function return exit export local readonly " +
            "source alias unset set echo cd sudo",
    ),
    powershell: words(
        "if else elseif switch foreach for while do until function param return break continue try catch finally " +
            "throw begin process end in filter class enum using",
    ),
    sql: words(
        "select from where insert into values update set delete create alter drop table index view join inner " +
            "left right outer full on as and or not null is in like between group by order having limit offset " +
            "union all distinct primary key foreign references default constraint unique case when then else end " +
            "exists begin commit rollback with returning asc desc true false",
    ),
    markup: new Set(),
    json: words("true false null"),
    plain: new Set(),
};

const STRING = String.raw`"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'`;
const TEMPLATE = "`(?:\\\\.|[^`\\\\])*`";
const NUMBER = String.raw`\b0x[\da-fA-F]+\b|\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b`;
const WORD = String.raw`[A-Za-z_][\w]*`;

const COMMENT: Record<Family, string> = {
    c: String.raw`\/\/[^\n]*|\/\*[\s\S]*?\*\/`,
    hash: String.raw`#[^\n]*`,
    shell: String.raw`#[^\n]*`,
    powershell: String.raw`<#[\s\S]*?#>|#[^\n]*`,
    sql: String.raw`--[^\n]*|\/\*[\s\S]*?\*\/`,
    markup: String.raw`<!--[\s\S]*?-->`,
    json: String.raw`\/\/[^\n]*`,
    plain: String.raw`(?!)`,
};

const patterns = new Map<Family, RegExp>();

function patternFor(family: Family): RegExp {
    let pattern = patterns.get(family);

    if (!pattern) {
        const parts = [
            `(?<comment>${COMMENT[family]})`,
            `(?<string>${STRING}${family === "c" ? `|${TEMPLATE}` : ""})`,
            family === "shell" || family === "powershell"
                ? String.raw`(?<variable>\$\{?[\w:]+\}?)`
                : "(?<variable>(?!))",
            family === "powershell" ? String.raw`(?<cmdlet>\b[A-Z][a-z]+-[A-Z][A-Za-z]+\b)` : "(?<cmdlet>(?!))",
            family === "markup" ? String.raw`(?<tag><\/?[A-Za-z][\w:-]*|\/?>)` : "(?<tag>(?!))",
            `(?<number>${NUMBER})`,
            `(?<word>${WORD})`,
        ];

        pattern = new RegExp(parts.join("|"), "g");
        patterns.set(family, pattern);
    }

    return pattern;
}

export function languageLabel(language: string | undefined): string {
    const name = (language ?? "").toLowerCase();

    return ALIASES[name] ?? name;
}

export function highlight(code: string, language: string | undefined): Token[] {
    const name = languageLabel(language);
    const family: Family = FAMILY[name] ?? "plain";
    const keywords = KEYWORDS[family];
    const caseInsensitive = family === "sql" || family === "powershell";
    const pattern = patternFor(family);
    const tokens: Token[] = [];
    let cursor = 0;

    pattern.lastIndex = 0;

    for (let match = pattern.exec(code); match; match = pattern.exec(code)) {
        if (match[0] === "") {
            pattern.lastIndex += 1;
            continue;
        }

        const groups = match.groups ?? {};
        let kind: TokenKind | undefined;

        if (groups.comment !== undefined) {
            kind = "comment";
        } else if (groups.string !== undefined) {
            // In JSON a string followed by a colon is a key.
            kind = family === "json" && /^\s*:/.test(code.slice(pattern.lastIndex)) ? "property" : "string";
        } else if (groups.variable !== undefined) {
            kind = "variable";
        } else if (groups.cmdlet !== undefined) {
            kind = "function";
        } else if (groups.tag !== undefined) {
            kind = "keyword";
        } else if (groups.number !== undefined) {
            kind = "number";
        } else if (groups.word !== undefined) {
            const word = caseInsensitive ? match[0].toLowerCase() : match[0];

            if (keywords.has(word)) {
                kind = "keyword";
            } else if (family !== "plain" && family !== "json" && code[pattern.lastIndex] === "(") {
                kind = "function";
            }
        }

        if (!kind) {
            continue;
        }

        if (match.index > cursor) {
            tokens.push({ text: code.slice(cursor, match.index) });
        }

        tokens.push({ text: match[0], kind });
        cursor = pattern.lastIndex;
    }

    if (cursor < code.length) {
        tokens.push({ text: code.slice(cursor) });
    }

    return tokens;
}
