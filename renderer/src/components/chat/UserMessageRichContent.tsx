/**
 * Adapted from eigent: ChatBox/MessageItem/UserMessageRichContent.tsx
 * Read-only rich body: {{skill}}, #skill, @connector, URLs.
 */
import {
  RICH_CONNECTOR_STYLE_CLASSES,
  RICH_SKILL_STYLE_CLASSES,
  hashSkillLabel,
  httpUrlOrNull,
  tokenizeRichPlainText,
} from "@/lib/richText";
import { cn } from "@/lib/utils";
import { Fragment, useMemo, type ReactNode } from "react";

const SKILL_TAG_REGEX = /\{\{([^}]+)\}\}/g;

type ContentNode =
  | { type: "text"; value: string }
  | { type: "skill"; name: string };

function parseContentWithTags(content: string): ContentNode[] {
  const nodes: ContentNode[] = [];
  let lastIndex = 0;
  SKILL_TAG_REGEX.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = SKILL_TAG_REGEX.exec(content)) !== null) {
    if (m.index > lastIndex) {
      nodes.push({ type: "text", value: content.slice(lastIndex, m.index) });
    }
    const inner = m[1].trim();
    if (inner.startsWith("@")) {
      nodes.push({ type: "text", value: m[0] });
    } else {
      nodes.push({ type: "skill", name: inner });
    }
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < content.length) {
    nodes.push({ type: "text", value: content.slice(lastIndex) });
  }
  return nodes.length > 0 ? nodes : [{ type: "text", value: content }];
}

const CHIP =
  "mx-0 inline rounded px-0.5 py-px align-baseline font-medium [font:inherit]";

function renderMessageRichSegments(
  text: string,
  keyPrefix: string,
  onOpenUrl?: (url: string) => void,
): ReactNode {
  return tokenizeRichPlainText(text).map((seg, i) => {
    const key = `${keyPrefix}-${i}`;
    if (seg.type === "text") {
      return <Fragment key={key}>{seg.text}</Fragment>;
    }
    if (seg.type === "url") {
      const href = httpUrlOrNull(seg.text);
      if (href) {
        return (
          <a
            key={key}
            href={href}
            target="_blank"
            rel="noreferrer"
            className="text-ds-text-information-default-default underline underline-offset-2 decoration-ds-border-information-default-default"
            onClick={(e) => {
              e.stopPropagation();
              if (onOpenUrl) {
                e.preventDefault();
                onOpenUrl(href);
              }
            }}
          >
            {seg.text}
          </a>
        );
      }
      return <Fragment key={key}>{seg.text}</Fragment>;
    }
    if (seg.type === "connector") {
      return (
        <span
          key={key}
          data-rich-connector="1"
          className={cn(CHIP, RICH_CONNECTOR_STYLE_CLASSES)}
        >
          {seg.text}
        </span>
      );
    }
    const clsIdx = hashSkillLabel(seg.text) % RICH_SKILL_STYLE_CLASSES.length;
    return (
      <span
        key={key}
        data-rich-skill="1"
        className={cn(CHIP, RICH_SKILL_STYLE_CLASSES[clsIdx])}
      >
        {seg.text}
      </span>
    );
  });
}

export function UserMessageRichContent({
  content,
  className,
  onOpenUrl,
}: {
  content: string;
  className?: string;
  onOpenUrl?: (url: string) => void;
}) {
  const nodes = useMemo(() => parseContentWithTags(content), [content]);

  return (
    <span className={cn("relative z-0 break-words whitespace-pre-wrap", className)}>
      {nodes.map((node, i) => {
        if (node.type === "text") {
          return (
            <Fragment key={`n${i}`}>
              {renderMessageRichSegments(node.value, `n${i}`, onOpenUrl)}
            </Fragment>
          );
        }
        const skillToken = `#${node.name}`;
        const clsIdx =
          hashSkillLabel(skillToken) % RICH_SKILL_STYLE_CLASSES.length;
        return (
          <span
            key={`n${i}`}
            data-rich-skill="1"
            className={cn(CHIP, RICH_SKILL_STYLE_CLASSES[clsIdx])}
          >
            {skillToken}
          </span>
        );
      })}
    </span>
  );
}
