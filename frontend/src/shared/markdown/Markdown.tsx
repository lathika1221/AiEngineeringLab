import { Fragment, isValidElement, memo, useState } from "react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { highlight, languageLabel } from "./highlight";
import { CELL_BREAK, CELL_LANG, normalizeMarkdown } from "./normalize";
import "./Markdown.css";

function textOf(node: ReactNode): string {
    if (typeof node === "string" || typeof node === "number") {
        return String(node);
    }

    if (Array.isArray(node)) {
        return node.map(textOf).join("");
    }

    if (isValidElement<{ children?: ReactNode }>(node)) {
        return textOf(node.props.children);
    }

    return "";
}

function Highlighted({ code, language }: { code: string; language?: string }) {
    return (
        <>
            {highlight(code, language).map((token, index) =>
                token.kind ? (
                    <span key={index} className={`tok-${token.kind}`}>
                        {token.text}
                    </span>
                ) : (
                    <Fragment key={index}>{token.text}</Fragment>
                ),
            )}
        </>
    );
}

function CodeBlock({ children }: { children?: ReactNode }) {
    const [copied, setCopied] = useState(false);

    const codeElement = isValidElement<{ className?: string }>(children) ? children : null;
    const language = /language-([\w+#.-]+)/.exec(codeElement?.props.className ?? "")?.[1];
    const code = textOf(children).replace(/\n$/, "");

    async function copy() {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
        } catch {
            setCopied(false);
        }
    }

    return (
        <div className="code-block">
            <div className="code-block__bar">
                <span>{languageLabel(language) || "code"}</span>
                <button
                    type="button"
                    className="code-block__copy"
                    onClick={() => void copy()}
                    aria-label={copied ? "Code copied" : "Copy code"}
                >
                    {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
                    {copied ? "Copied" : "Copy"}
                </button>
            </div>
            <pre tabIndex={0}>
                <code>
                    <Highlighted code={code} language={language} />
                </code>
            </pre>
        </div>
    );
}

/** Inline code. Code that came from a fenced block inside a table cell keeps its lines. */
function InlineCode({ children, className }: { children?: ReactNode; className?: string }) {
    const raw = textOf(children);

    if (!raw.includes(CELL_BREAK) && !raw.includes(CELL_LANG)) {
        return <code className={className}>{children}</code>;
    }

    const languageMatch = new RegExp(`^${CELL_LANG}([^${CELL_LANG}]*)${CELL_LANG}`).exec(raw);
    const language = languageMatch?.[1];
    const code = raw.slice(languageMatch?.[0].length ?? 0).split(CELL_BREAK).join("\n");

    return (
        <code className="cell-code">
            <Highlighted code={code} language={language} />
        </code>
    );
}

/** Turns cell line-break markers in plain text back into real line breaks. */
function withCellBreaks(children: ReactNode): ReactNode {
    if (typeof children === "string") {
        if (!children.includes(CELL_BREAK)) {
            return children;
        }

        const parts = children.split(CELL_BREAK);

        return parts.map((part, index) => (
            <Fragment key={index}>
                {part}
                {index < parts.length - 1 && <br />}
            </Fragment>
        ));
    }

    if (Array.isArray(children)) {
        return children.map((child, index) => <Fragment key={index}>{withCellBreaks(child)}</Fragment>);
    }

    return children;
}

const components: Components = {
    pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
    code: ({ children, className }) => <InlineCode className={className}>{children}</InlineCode>,
    table: ({ children }) => (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Table">
            <table>{children}</table>
        </div>
    ),
    td: ({ children, style }) => <td style={style}>{withCellBreaks(children)}</td>,
    th: ({ children, style }) => <th style={style}>{withCellBreaks(children)}</th>,
    strong: ({ children }) => <strong>{withCellBreaks(children)}</strong>,
    em: ({ children }) => <em>{withCellBreaks(children)}</em>,
    a: ({ children, href }) => (
        <a href={href} target="_blank" rel="noreferrer noopener">
            {children}
        </a>
    ),
    // Addresses the sanitiser rejects (data:, javascript:) arrive empty: show the description instead.
    img: ({ src, alt }) =>
        src ? <img src={src} alt={alt ?? ""} loading="lazy" /> : <span className="image-missing">{alt}</span>,
};

const plugins = [remarkGfm];

/**
 * Renders model output as Markdown.
 * Memoised: while a reply streams, only the message that is changing re-parses.
 */
const Markdown = memo(function Markdown({ children }: { children: string }) {
    return (
        <div className="markdown">
            <ReactMarkdown remarkPlugins={plugins} components={components}>
                {normalizeMarkdown(children)}
            </ReactMarkdown>
        </div>
    );
});

export default Markdown;
