/**
 * Adapted from eigent: ChatBox/MessageItem/AgentMessageCard + MarkDown.
 * V1 deep-think: one collapsible summary per assistant bubble, then answers.
 */
import { useMemo, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { isWorkforceProcessMeta } from "@/store/session";
import { cn } from "@/lib/utils";

import MarkdownView from "./markdown/MarkdownView";

interface MessageContentProps {
  content: string;
  role?: "user" | "assistant";
  className?: string;
  /** When true, keep the latest unclosed think expanded (streaming). */
  streaming?: boolean;
  /** Skip think UI when a parent already rendered a turn-level summary. */
  hideThink?: boolean;
}

export type ThinkSegment = { type: "think"; text: string; closed: boolean };
export type ContentSegment =
  | ThinkSegment
  | { type: "answer"; text: string };

/** Drop unsolicited Word/officecli plans from deep-think (research defaults to Markdown). */
const OFFICE_THINK_RE =
  /officecli|生成正式的\s*Word|生成\s*Word\s*文档|写一份\s*Word|正式的\s*Word|page\s*layout|pageBreakBefore/i;

export function sanitizeThinkText(text: string): string {
  const raw = text || "";
  const parts = raw.split(/(?<=[。！？\n])/);
  return parts
    .filter((part) => part.trim() && !OFFICE_THINK_RE.test(part))
    .join("")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Split content into think/answer segments in document order. */
export function parseContentSegments(content: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  let remaining = content;
  while (remaining.length) {
    const openMatch = remaining.match(/<think>/i);
    if (!openMatch || openMatch.index == null) {
      const text = remaining.replace(/<\/?think>/gi, "").trim();
      if (text) segments.push({ type: "answer", text });
      break;
    }
    const before = remaining
      .slice(0, openMatch.index)
      .replace(/<\/?think>/gi, "")
      .trim();
    if (before) segments.push({ type: "answer", text: before });
    remaining = remaining.slice(openMatch.index + openMatch[0].length);
    const closeMatch = remaining.match(/<\/think>/i);
    if (!closeMatch || closeMatch.index == null) {
      const text = sanitizeThinkText(remaining.trim());
      if (text) segments.push({ type: "think", text, closed: false });
      break;
    }
    const thinkBody = sanitizeThinkText(remaining.slice(0, closeMatch.index).trim());
    if (thinkBody) {
      segments.push({ type: "think", text: thinkBody, closed: true });
    }
    remaining = remaining.slice(closeMatch.index + closeMatch[0].length);
  }
  return segments;
}

export function collectThinkSegments(content: string): ThinkSegment[] {
  return parseContentSegments(content).filter(
    (s): s is ThinkSegment => s.type === "think",
  );
}

export function hasVisibleAnswer(content: string): boolean {
  for (const s of parseContentSegments(content)) {
    if (s.type === "answer" && cleanAnswerSegment(s.text)) return true;
  }
  return false;
}

/** @deprecated Prefer parseContentSegments — kept for callers that only need thinks+blob. */
export function parseThinkBlocks(content: string): {
  thinks: Array<{ text: string; closed: boolean }>;
  answer: string;
} {
  const segments = parseContentSegments(content);
  return {
    thinks: segments
      .filter((s): s is ThinkSegment => s.type === "think")
      .map((s) => ({ text: s.text, closed: s.closed })),
    answer: segments
      .filter((s): s is Extract<ContentSegment, { type: "answer" }> => s.type === "answer")
      .map((s) => s.text)
      .join("\n\n")
      .trim(),
  };
}

/** One collapsible think block (V1: a single summary, not one row per step). */
export function ThinkBlock({
  think,
  label,
}: {
  think: ThinkSegment;
  label?: string;
}) {
  const live = !think.closed;
  const title = label ?? (live ? "思考中…" : "深度思考");
  return (
    <details
      className="group deep-think"
      {...(live ? { open: true } : {})}
    >
      <summary className="cursor-pointer select-none list-none text-[13px] text-ds-text-neutral-muted-default marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="inline-flex items-center gap-1.5">
          <span className="text-ds-text-neutral-subtle-default transition-transform group-open:rotate-90">
            ▸
          </span>
          {title}
        </span>
      </summary>
      <div className="mt-1.5 border-l-2 border-ds-border-neutral-subtle-default pl-3 text-[13px] leading-[1.65] text-ds-text-neutral-muted-default whitespace-pre-wrap">
        {think.text}
        {live ? <span className="animate-pulse">|</span> : null}
      </div>
    </details>
  );
}

/** Merge every think in the bubble into one V1 summary. */
export function ThinkSummary({ thinks }: { thinks: ThinkSegment[] }) {
  if (thinks.length === 0) return null;
  const live = thinks.some((t) => !t.closed);
  const text = thinks
    .map((t) => t.text.trim())
    .filter(Boolean)
    .join("\n\n");
  if (!text && !live) return null;
  const merged: ThinkSegment = { type: "think", text, closed: !live };
  const label = live
    ? "思考中…"
    : thinks.length > 1
      ? `已思考 · ${thinks.length} 步`
      : "深度思考";
  return <ThinkBlock think={merged} label={label} />;
}

function cleanAnswerSegment(text: string): string {
  let t = text.replace(/<summary>([\s\S]*?)<\/summary>/gi, "$1");
  // Strip leftover structural tags the model may emit — the paired regex above
  // misses malformed/unpaired cases (e.g. a stray "</summary>").
  t = t.replace(/<\/?(?:details|summary)>/gi, "");
  // Streaming: drop a trailing partial tag fragment like "<summary" or "</details".
  t = t.replace(/<\/?[a-zA-Z][^>]*$/, "");
  t = t.trim();
  if (!t || isWorkforceProcessMeta(t)) return "";
  return t;
}

/** Repair GFM so remark can parse blocks the model glued to the previous line. */
export function normalizeMarkdown(md: string): string {
  if (!md) return md;
  return md
    .split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g)
    .map((chunk, i) => (i % 2 === 1 ? chunk : normalizeMarkdownProse(chunk)))
    .join("");
}

function normalizeMarkdownProse(md: string): string {
  let out = normalizeMarkdownTableBlocks(md);
  // `机制### 2. 标题` — ATX h2–h6 must start a line (avoid splitting `C# ` / table cells).
  out = out.replace(/([^\n|#])(#{2,6}[ \t]+\S)/g, "$1\n\n$2");
  out = out.replace(
    /([\u4e00-\u9fff。，；：、！？）】》」』])(#[ \t]+\S)/g,
    "$1\n\n$2",
  );
  out = out.replace(/(#{1,6}[ \t][^\n]*[\u4e00-\u9fff])([-*+] )/g, "$1\n$2");
  return out;
}

function isTableSeparator(line: string): boolean {
  const t = line.trim();
  return t.includes("|") && /-{3,}/.test(t) && /^[\s|:-]+$/.test(t);
}

function isTableDataRow(line: string): boolean {
  const t = line.trim();
  return t.startsWith("|") && t.includes("|", 1) && !isTableSeparator(t);
}

function splitRowCells(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) => c.trim());
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
    if (next !== undefined && isTableSeparator(next) && line.includes("|")) {
      const body: string[] = [];
      let j = i + 2;
      while (j < lines.length && isTableDataRow(lines[j])) {
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

/** @deprecated Use normalizeMarkdown — kept for FilePreview / existing tests. */
export function normalizeMarkdownTables(md: string): string {
  return normalizeMarkdown(md);
}

const markdownComponents = {
  table: ({ children, ...props }: ComponentPropsWithoutRef<"table">) => (
    <div className="md-table-wrap my-4 w-full overflow-x-auto rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default shadow-[var(--shadow-button)]">
      <table
        {...props}
        className="w-full min-w-[36rem] border-separate border-spacing-0 text-left text-[13px] leading-[1.55]"
      >
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }: ComponentPropsWithoutRef<"thead">) => (
    <thead {...props}>{children}</thead>
  ),
  tbody: ({ children, ...props }: ComponentPropsWithoutRef<"tbody">) => (
    <tbody {...props}>{children}</tbody>
  ),
  tr: ({ children, ...props }: ComponentPropsWithoutRef<"tr">) => (
    <tr {...props}>{children}</tr>
  ),
  th: ({ children, ...props }: ComponentPropsWithoutRef<"th">) => (
    <th {...props}>{children}</th>
  ),
  td: ({ children, ...props }: ComponentPropsWithoutRef<"td">) => (
    <td {...props}>{children}</td>
  ),
  hr: ({ ...props }: ComponentPropsWithoutRef<"hr">) => (
    <hr
      {...props}
      className="my-4 border-0 border-t border-ds-border-neutral-subtle-default"
    />
  ),
};

export { markdownComponents };

const CODE_STYLE = { marginTop: 4, marginBlock: 4 };

const answerClassName = cn(
  "markdown-body max-w-none overflow-x-auto font-['Inter'] text-[14px] leading-[1.65] text-ds-text-neutral-default-default",
  "[&_a]:text-ds-text-neutral-default-default [&_a]:underline",
  "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-ds-border-neutral-subtle-default [&_blockquote]:pl-3 [&_blockquote]:text-ds-text-neutral-muted-default",
  "[&_code]:rounded [&_code]:bg-ds-bg-neutral-subtle-default [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[12px]",
  "[&_h1]:mb-2 [&_h1]:mt-4 [&_h1]:text-[18px] [&_h1]:font-bold",
  "[&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-[16px] [&_h2]:font-bold",
  "[&_h3]:mb-1.5 [&_h3]:mt-3 [&_h3]:text-[14px] [&_h3]:font-semibold",
  "[&_li]:my-0.5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5",
  "[&_p]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-ds-bg-neutral-subtle-default [&_pre]:p-3",
  "[&_strong]:font-semibold [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5",
);

export default function MessageContent({
  content,
  role = "assistant",
  className,
  streaming: _streaming = false,
  hideThink = false,
}: MessageContentProps) {
  const segments = useMemo((): ContentSegment[] => {
    if (role === "user") return [{ type: "answer", text: content }];
    return parseContentSegments(content);
  }, [content, role]);

  const visible = useMemo(() => {
    return segments
      .map((seg) => {
        if (seg.type === "think") return seg;
        const text = normalizeMarkdown(cleanAnswerSegment(seg.text));
        return text ? ({ type: "answer" as const, text }) : null;
      })
      .filter(Boolean) as ContentSegment[];
  }, [segments]);

  const shown = hideThink
    ? visible.filter((s) => s.type === "answer")
    : visible;

  const thinks = shown.filter((s): s is ThinkSegment => s.type === "think");
  const answers = shown.filter(
    (s): s is Extract<ContentSegment, { type: "answer" }> => s.type === "answer",
  );

  if (thinks.length === 0 && answers.length === 0) return null;

  return (
    <div className={cn("flex w-full min-w-0 flex-col gap-2", className)}>
      {!hideThink ? <ThinkSummary thinks={thinks} /> : null}
      {answers.map((seg, index) => (
        <div
          key={`answer-${index}`}
          className="w-full min-w-0 [&_.aion-md>p:first-child]:mt-0 [&_.aion-md>p:last-child]:mb-0"
        >
          <MarkdownView codeStyle={CODE_STYLE}>{seg.text}</MarkdownView>
        </div>
      ))}
    </div>
  );
}
