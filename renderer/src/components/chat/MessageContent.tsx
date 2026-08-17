/**
 * Adapted from eigent: ChatBox/MessageItem/AgentMessageCard + MarkDown.
 * Renders WorkBuddy-style deep-think: each <think> stays next to the step it belongs to.
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
      const text = remaining.trim();
      if (text) segments.push({ type: "think", text, closed: false });
      break;
    }
    const thinkBody = remaining.slice(0, closeMatch.index).trim();
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

/** One collapsible WorkBuddy-style think block for a single step. */
export function ThinkBlock({ think }: { think: ThinkSegment }) {
  const live = !think.closed;
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
          {live ? "思考中…" : "深度思考"}
        </span>
      </summary>
      <div className="mt-1.5 border-l-2 border-ds-border-neutral-subtle-default pl-3 text-[13px] leading-[1.65] text-ds-text-neutral-muted-default whitespace-pre-wrap">
        {think.text}
        {live ? <span className="animate-pulse">|</span> : null}
      </div>
    </details>
  );
}

/** Sequential think blocks — one per step, not a single merged summary. */
export function ThinkSummary({ thinks }: { thinks: ThinkSegment[] }) {
  if (thinks.length === 0) return null;
  return (
    <div className="flex w-full min-w-0 flex-col gap-2">
      {thinks.map((think, i) => (
        <ThinkBlock key={i} think={think} />
      ))}
    </div>
  );
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

/** Ensure GFM tables have a blank line before them so remark parses reliably. */
export function normalizeMarkdownTables(md: string): string {
  if (!md || !md.includes("|")) return md;
  const flushTable = new RegExp("([^\\n])\\n(\\|[^\\n]+\\|\\s*\\n\\|[-:| \\t]+\\|)", "g");
  return md.replace(flushTable, "$1\n\n$2");
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
        const text = normalizeMarkdownTables(cleanAnswerSegment(seg.text));
        return text ? ({ type: "answer" as const, text }) : null;
      })
      .filter(Boolean) as ContentSegment[];
  }, [segments]);

  const shown = hideThink
    ? visible.filter((s) => s.type === "answer")
    : visible;

  if (shown.length === 0) return null;

  return (
    <div className={cn("flex w-full min-w-0 flex-col gap-2", className)}>
      {shown.map((seg, index) =>
        seg.type === "think" ? (
          <ThinkBlock key={`think-${index}`} think={seg} />
        ) : (
          <div
            key={`answer-${index}`}
            className="w-full min-w-0 [&_.aion-md>p:first-child]:mt-0 [&_.aion-md>p:last-child]:mb-0"
          >
            <MarkdownView codeStyle={CODE_STYLE}>{seg.text}</MarkdownView>
          </div>
        ),
      )}
    </div>
  );
}
