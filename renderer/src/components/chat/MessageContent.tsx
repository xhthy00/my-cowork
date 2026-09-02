/**
 * Adapted from eigent: ChatBox/MessageItem/AgentMessageCard + MarkDown.
 * V1 deep-think: one collapsible summary per assistant bubble, then answers.
 */
import { useEffect, useMemo, useRef, useState, type ComponentPropsWithoutRef } from "react";

import { isWorkforceProcessMeta } from "@/store/session";
import { stripProcessNarration } from "@/lib/processNarration";
import { cn } from "@/lib/utils";

import MarkdownView from "./markdown/MarkdownView";
import {
  normalizeMarkdown,
  normalizeMarkdownTables,
} from "./markdown/normalizeMarkdown";

export { normalizeMarkdown, normalizeMarkdownTables };

interface MessageContentProps {
  content: string;
  role?: "user" | "assistant";
  className?: string;
  /** When true, keep the latest unclosed think expanded (streaming). */
  streaming?: boolean;
  /** Skip think UI when a parent already rendered a turn-level summary. */
  hideThink?: boolean;
  /** Eigent END card: render markdown as-is (no process-narration strip). */
  verbatim?: boolean;
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

function dropProcessNarration(segments: ContentSegment[]): ContentSegment[] {
  return segments.flatMap((s) => {
    if (s.type !== "answer") return [s];
    const text = stripProcessNarration(s.text);
    return text ? [{ type: "answer" as const, text }] : [];
  });
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
  return dropProcessNarration(segments);
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

/** One collapsible process block (WorkBuddy: expand while live, collapse when done). */
export function ThinkBlock({
  think,
  label,
}: {
  think: ThinkSegment;
  label?: string;
}) {
  const live = !think.closed;
  const title = label ?? (live ? "思考中…" : "工作过程");
  const bodyRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(live);

  useEffect(() => {
    setOpen(live);
  }, [live]);

  useEffect(() => {
    if (!live) return;
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [live, think.text]);

  return (
    <details
      className="group deep-think"
      open={open}
      onToggle={(e) => {
        const next = (e.currentTarget as HTMLDetailsElement).open;
        if (live) {
          setOpen(true);
          return;
        }
        setOpen(next);
      }}
    >
      <summary className="cursor-pointer select-none list-none text-[13px] text-ds-text-neutral-muted-default marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="inline-flex items-center gap-1.5">
          <span className="text-ds-text-neutral-subtle-default transition-transform group-open:rotate-90">
            ▸
          </span>
          {title}
        </span>
      </summary>
      <div
        ref={bodyRef}
        className="mt-1.5 max-h-[220px] overflow-y-auto border-l-2 border-ds-border-neutral-subtle-default pl-3 text-[13px] leading-[1.65] text-ds-text-neutral-muted-default whitespace-pre-wrap"
      >
        {think.text}
        {live ? <span className="animate-pulse">|</span> : null}
      </div>
    </details>
  );
}

/** Merge every think in the bubble into one process summary. */
export function ThinkSummary({ thinks }: { thinks: ThinkSegment[] }) {
  if (thinks.length === 0) return null;
  const live = thinks.some((t) => !t.closed);
  const text = thinks
    .map((t) => t.text.trim())
    .filter(Boolean)
    .join("\n\n");
  if (!text && !live) return null;
  const merged: ThinkSegment = { type: "think", text, closed: !live };
  const label = live ? "思考中…" : "工作过程";
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
  t = stripProcessNarration(t);
  return t;
}

/** Chat bubble: headings, source quotes, then GFM repairs. */
export function beautifyChatMarkdown(md: string): string {
  if (!md) return md;
  return promoteNumberedTitles(
    flattenNumberedSections(
      quoteSourceLines(promoteLeadingTitle(normalizeMarkdown(md))),
    ),
  );
}

const NUMBERED_SECTION_RE =
  /^([ \t\u3000]*)(?:#{1,6}[ \t]+)?(?:\*\*[ \t]*)?(\d+)(?:[.)]|、|．)(?:[ \t]*\*\*)?[ \t]+(.*)$/;

/**
 * LLM answers often indent `2.` / `3.` under item 1, which CommonMark
 * treats as nested lists (staircase). Pull sequential 2,3,4… back to column 0.
 * Leave a nested restart (`   1.`) indented.
 */
export function flattenNumberedSections(md: string): string {
  return md
    .split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g)
    .map((chunk, i) => (i % 2 === 1 ? chunk : flattenNumberedSectionProse(chunk)))
    .join("");
}

function flattenNumberedSectionProse(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let lastTop = 0;
  let nestedLast = 0;
  for (const line of lines) {
    if (/^\s{0,3}#{1,6}\s+\S/.test(line) && !NUMBERED_SECTION_RE.test(line)) {
      lastTop = 0;
      nestedLast = 0;
      out.push(line);
      continue;
    }
    const m = NUMBERED_SECTION_RE.exec(line);
    if (!m) {
      out.push(line);
      continue;
    }
    const indent = m[1];
    const n = Number(m[2]);
    const wrapped = /^\s*\*\*/.test(line);
    const rest = wrapped
      ? String(m[3] || "").replace(/\*\*\s*$/, "").trim()
      : String(m[3] || "").trim();
    if (n === 1 && indent.length > 0 && lastTop >= 1) {
      out.push(line);
      nestedLast = 1;
      continue;
    }
    if (indent.length > 0 && nestedLast >= 1 && n === nestedLast + 1) {
      out.push(line);
      nestedLast = n;
      continue;
    }
    if (n === 1 || n === lastTop + 1) {
      const body = wrapped && rest && !rest.startsWith("**") ? `**${rest}**` : rest;
      out.push(`${n}. ${body}`);
      lastTop = n;
      nestedLast = 0;
      continue;
    }
    out.push(line);
  }
  return out.join("\n");
}

/** `1. **已中签者——分批兑现**` is a section title, not a one-item grey card. */
const NUMBERED_TITLE_RE = /^(\d+)\.\s+\*\*(.+?)\*\*\s*$/;

function promoteNumberedTitles(md: string): string {
  return md
    .split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g)
    .map((chunk, i) => (i % 2 === 1 ? chunk : promoteNumberedTitleProse(chunk)))
    .join("");
}

function promoteNumberedTitleProse(md: string): string {
  return md
    .split("\n")
    .map((line) => {
      const m = NUMBERED_TITLE_RE.exec(line);
      if (!m) return line;
      const title = m[2].trim();
      if (!title || title.length > 80) return line;
      if (/[。！？]$/.test(title)) return line;
      return `### ${m[1]}. ${title}`;
    })
    .join("\n");
}

function promoteLeadingTitle(md: string): string {
  const match = /^(?:[ \t]*\n)*([^\n]+)/.exec(md);
  if (!match) return md;
  const line = match[1].trim();
  if (line.length < 4 || line.length > 48) return md;
  if (/^#{1,6}\s/.test(line)) return md;
  if (/^([-*+]|\d+[.)])\s/.test(line)) return md;
  if (/^[>`|]/.test(line) || /```/.test(line)) return md;
  if (/[。！？]$/.test(line)) return md;
  return md.replace(match[1], (raw) => raw.replace(line, `## ${line}`));
}

function quoteSourceLines(md: string): string {
  return md.replace(
    /^([ \t]*)(?:[-*+]\s+)?来源[：:]\s*(\S.*)$/gm,
    (_full, indent: string, rest: string) => {
      const body = rest.trim();
      if (!body || body.startsWith(">")) return `${indent}来源：${body}`;
      return `${indent}> **来源** · ${body}`;
    },
  );
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
  verbatim = false,
}: MessageContentProps) {
  const segments = useMemo((): ContentSegment[] => {
    if (role === "user" || verbatim) return [{ type: "answer", text: content }];
    return parseContentSegments(content);
  }, [content, role, verbatim]);

  const visible = useMemo(() => {
    return segments
      .map((seg) => {
        if (seg.type === "think") return seg;
        const text = beautifyChatMarkdown(
          verbatim ? seg.text : cleanAnswerSegment(seg.text),
        );
        return text ? ({ type: "answer" as const, text }) : null;
      })
      .filter(Boolean) as ContentSegment[];
  }, [segments, verbatim]);

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
