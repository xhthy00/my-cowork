/**
 * Repair LLM markdown so remark-gfm can parse it (glued fences, broken tables).
 */

function isStandaloneFenceLine(line: string): boolean {
  return /^\s{0,3}(?:```+|~~~+)[a-zA-Z0-9_+-]*\s*$/.test(line);
}

/** `标题```` / `正文```` → fence on its own line so CommonMark can parse it. */
function detachGluedCodeFences(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let inFence = false;
  for (const line of lines) {
    if (isStandaloneFenceLine(line)) {
      out.push(line);
      inFence = !inFence;
      continue;
    }
    if (inFence) {
      const close = /^(.*\S)\s*(```+|~~~+)\s*$/.exec(line);
      if (close) {
        out.push(close[1]);
        out.push(close[2]);
        inFence = false;
        continue;
      }
      out.push(line);
      continue;
    }
    const open = /^(.*\S)\s*(```+|~~~+)([a-zA-Z0-9_+-]*)(?:\s+(\S.*))?$/.exec(line);
    if (open) {
      out.push(open[1]);
      out.push(`${open[2]}${open[3] || ""}`);
      if (open[4]) out.push(open[4]);
      inFence = true;
      continue;
    }
    out.push(line);
  }
  return out.join("\n");
}

/** Fullwidth pipe → GFM ascii. Do not touch em/en dashes in prose titles. */
function asciiTableGlyphs(md: string): string {
  return md.replace(/\uFF5C/g, "|");
}

/** `| - 通关系统` is a list item the model prefixed with a stray pipe. */
function stripFalseTableListPrefix(md: string): string {
  return md.replace(/^( *)\|\s+([-*+]|\d+[.)])(\s)/gm, "$1$2$3");
}

function normalizeMarkdownProse(md: string): string {
  let out = asciiTableGlyphs(md);
  out = stripFalseTableListPrefix(out);
  out = normalizeMarkdownTableBlocks(out);
  // `机制### 2. 标题` — ATX h2–h6 must start a line (avoid splitting `C# ` / table cells).
  out = out.replace(/([^\n|#])(#{2,6}[ \t]+\S)/g, "$1\n\n$2");
  out = out.replace(
    /([\u4e00-\u9fff。，；：、！？）】》」』])(#[ \t]+\S)/g,
    "$1\n\n$2",
  );
  out = out.replace(/(#{1,6}[ \t][^\n]*[\u4e00-\u9fff])([-*+] )/g, "$1\n$2");
  out = stripStreamingArtifacts(out);
  return out;
}

/** MiniMax often leaks a stray closer or a half-typed tag while streaming. */
function stripStreamingArtifacts(md: string): string {
  let out = md.replace(/^(?:\s*<\/[a-zA-Z][\w:-]*>\s*)+/g, "");
  out = out.replace(/<\/?[a-zA-Z][^>]*$/g, "");
  return out;
}

function isTableSeparator(line: string): boolean {
  const t = line.trim().replace(/[\u2013\u2014\u2212]/g, "-");
  return t.includes("|") && /-{3,}/.test(t) && /^[\s|:-]+$/.test(t);
}

function splitRowCells(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) => c.trim());
}

function looksLikeTableRow(line: string): boolean {
  const t = line.trim();
  if (!t || isTableSeparator(t)) return false;
  if (t.startsWith("|") && t.includes("|", 1)) return true;
  const cells = splitRowCells(t);
  return cells.length >= 2 && cells.some((c) => c.length > 0);
}

function joinRow(cells: string[]): string {
  return `| ${cells.join(" | ")} |`;
}

function makeSeparator(cols: number): string {
  return `|${Array.from({ length: cols }, () => "---").join("|")}|`;
}

function isTitleCell(cell: string): boolean {
  return /^\s*#{1,6}\s+\S/.test(cell) || /^\s*\d+[.\u3001\uFF0E]\s+\S/.test(cell);
}

function padRow(cells: string[], cols: number): string[] {
  const row = cells.slice(0, cols);
  while (row.length < cols) row.push("");
  return row;
}

function rewriteTable(
  headerLine: string,
  _sepLine: string,
  bodyLines: string[],
): { title: string | null; lines: string[] } {
  const header = splitRowCells(headerLine);
  const body = bodyLines.map(splitRowCells);
  const sepCols = splitRowCells(_sepLine).length;
  const bodyCols = body[0]?.length ?? sepCols;
  let title: string | null = null;
  if (
    header.length === bodyCols + 1 &&
    (sepCols === bodyCols || sepCols === header.length) &&
    header[0] &&
    isTitleCell(header[0])
  ) {
    title = header.shift() ?? null;
  }
  const cols = Math.max(header.length, sepCols, bodyCols, 1);
  return {
    title,
    lines: [
      joinRow(padRow(header, cols)),
      makeSeparator(cols),
      ...body.map((row) => joinRow(padRow(row, cols))),
    ],
  };
}

function normalizeMarkdownTableBlocks(md: string): string {
  if (!md.includes("|")) return md;
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1];
    if (next !== undefined && isTableSeparator(next) && looksLikeTableRow(line)) {
      const body: string[] = [];
      let j = i + 2;
      while (j < lines.length && looksLikeTableRow(lines[j])) {
        body.push(lines[j]);
        j++;
      }
      const { title, lines: tableLines } = rewriteTable(line, next, body);
      const prev = out.length ? out[out.length - 1] : "";
      if (prev.trim() !== "") out.push("");
      if (title) {
        out.push(title);
        out.push("");
      }
      out.push(...tableLines);
      i = j;
      continue;
    }
    out.push(line);
    i++;
  }
  return out.join("\n");
}

/** Repair GFM so remark can parse blocks the model glued to the previous line. */
export function normalizeMarkdown(md: string): string {
  if (!md) return md;
  const detached = detachGluedCodeFences(md);
  return detached
    .split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g)
    .map((chunk, i) => (i % 2 === 1 ? chunk : normalizeMarkdownProse(chunk)))
    .join("");
}

/** @deprecated Use normalizeMarkdown — kept for FilePreview / existing tests. */
export function normalizeMarkdownTables(md: string): string {
  return normalizeMarkdown(md);
}
