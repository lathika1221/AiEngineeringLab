/**
 * Repairs model output before it reaches the Markdown parser.
 *
 * GitHub-flavoured tables are one line per row, so they cannot hold fenced code
 * blocks or line breaks. Models write them anyway, in three shapes:
 *
 *   | Step | ```powershell\nGet-Process\n``` |      literal backslash-n
 *   | Step | ```powershell<br>Get-Process<br>``` |  <br> tags
 *   | Step | ```powershell                          a real newline, which splits
 *   Get-Process                                     the row and breaks the table
 *   ``` |
 *
 * Left alone these show raw fences and "\n" text. Here each such cell is turned
 * into inline code whose line breaks are carried by a private marker character;
 * the renderer turns the marker back into real line breaks.
 */

/** Stands for a line break inside a table cell. */
export const CELL_BREAK = "\uE000";

/** Wraps the language name at the start of code that came from a fenced block in a cell. */
export const CELL_LANG = "\uE001";

const BR_TAG = /<br\s*\/?>/gi;
const CELL_FENCE = new RegExp(
    "```([\\w+#.-]*)[ \\t]*" + CELL_BREAK + "?([\\s\\S]*?)" + CELL_BREAK + "?[ \\t]*```",
    "g",
);

function countFences(line: string): number {
    return line.split("```").length - 1;
}

function isTableRow(line: string): boolean {
    return /^\s*\|/.test(line);
}

function normalizeRow(row: string): string {
    const withBreaks = row.replace(BR_TAG, CELL_BREAK);

    return withBreaks.replace(CELL_FENCE, (_match, language: string, rawBody: string) => {
        const body = rawBody
            .replace(/(?:\\r)?\\n/g, CELL_BREAK)
            .replace(new RegExp(`^${CELL_BREAK}+|${CELL_BREAK}+$`, "g"), "")
            // A bare pipe would end the cell; GFM unescapes "\|" inside code.
            .replace(/(?<!\\)\|/g, "\\|");

        const delimiter = body.includes("`") ? "``" : "`";
        const languageTag = language ? `${CELL_LANG}${language}${CELL_LANG}` : "";

        return `${delimiter} ${languageTag}${body} ${delimiter}`;
    });
}

export function normalizeMarkdown(source: string): string {
    const lines = source.replace(/\r\n?/g, "\n").split("\n");
    const output: string[] = [];
    let openFence: string | null = null;

    for (let index = 0; index < lines.length; index += 1) {
        let line = lines[index];
        const fence = /^\s{0,3}(`{3,}|~{3,})/.exec(line)?.[1] ?? null;

        if (openFence) {
            output.push(line);

            if (
                fence &&
                fence[0] === openFence[0] &&
                fence.length >= openFence.length &&
                line.trim() === fence
            ) {
                openFence = null;
            }

            continue;
        }

        if (isTableRow(line)) {
            // A fence opened inside a cell with a real newline: pull the following
            // lines back into this row until the fence closes.
            while (countFences(line) % 2 === 1 && index + 1 < lines.length) {
                index += 1;
                line += CELL_BREAK + lines[index];
            }

            output.push(normalizeRow(line));
            continue;
        }

        if (fence) {
            openFence = fence;
            output.push(line);
            continue;
        }

        // Outside tables and code, a <br> is a plain line break.
        output.push(line.replace(BR_TAG, "\n"));
    }

    return output.join("\n");
}
