/**
 * Ported from AionUi (packages/desktop/src/renderer/components/Markdown/CodeBlock.tsx).
 * Apache-2.0 © AionUi — icons swapped from icon-park to lucide-react,
 * arco Message replaced with silent clipboard fallback.
 */
import katex from "katex";
import { Copy, ChevronDown, ChevronUp } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import SyntaxHighlighter from "react-syntax-highlighter";
import { vs, vs2015 } from "react-syntax-highlighter/dist/esm/styles/hljs";

import { readDocumentTheme } from "@/lib/appearance";
import MermaidBlock from "./MermaidBlock";
import { formatCode, getDiffLineStyle } from "./markdownUtils";

const PREVIEW_LINES = 3;
// code span: font-size 13px, line-height 20px (per markdown css)
const CODE_LINE_HEIGHT = 20;
// SyntaxHighlighter pre padding: 0.5em top + 0.5em bottom ≈ 13px each side
const CODE_PADDING_VERTICAL = 13;
const COLLAPSED_HEIGHT = PREVIEW_LINES * CODE_LINE_HEIGHT + CODE_PADDING_VERTICAL;

async function copyText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

type CodeBlockProps = {
  children: string;
  className?: string;
  node?: unknown;
  hiddenCodeCopyButton?: boolean;
  codeStyle?: React.CSSProperties;
  [key: string]: unknown;
};

function CodeBlock(props: CodeBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [currentTheme, setCurrentTheme] = useState<"light" | "dark">(
    () => readDocumentTheme(),
  );

  useEffect(() => {
    const update = () => setCurrentTheme(readDocumentTheme());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });
    return () => observer.disconnect();
  }, []);

  const toggleExpanded = () => {
    const willCollapse = expanded;
    setExpanded((v) => !v);
    if (willCollapse && containerRef.current) {
      requestAnimationFrame(() => {
        containerRef.current?.scrollIntoView({ block: "nearest", behavior: "auto" });
      });
    }
  };

  const { children, className, node: _node, hiddenCodeCopyButton, codeStyle, ...rest } = props;
  const match = /language-(\w+)/.exec(className || "");
  const language = match?.[1] || "text";

  // KaTeX math blocks
  if (language === "latex" || language === "math" || language === "tex") {
    const latexSource = String(children).replace(/\n$/, "");
    const isFullDocument = /\\(documentclass|begin\{document\}|usepackage)\b/.test(latexSource);
    if (!isFullDocument) {
      try {
        const html = katex.renderToString(latexSource, { displayMode: true, throwOnError: false });
        return <div className="katex-display" dangerouslySetInnerHTML={{ __html: html }} />;
      } catch {
        // fall through
      }
    }
  }

  if (language === "mermaid") {
    return <MermaidBlock code={formatCode(children)} style={codeStyle} />;
  }

  // Inline code (single line)
  if (!String(children).includes("\n")) {
    return (
      <code {...rest} className={className} style={{ fontWeight: "bold" }}>
        {children}
      </code>
    );
  }

  const isDiff = language === "diff";
  const formattedContent = formatCode(children);
  const totalLines = formattedContent.split("\n").length;
  const canCollapse = totalLines > PREVIEW_LINES;
  const codeTheme = currentTheme === "dark" ? vs2015 : vs;
  const diffLines = isDiff ? formattedContent.split("\n") : [];
  const isDark = currentTheme === "dark";

  const handleCopy = () => {
    void copyText(formattedContent).catch(() => {
      /* clipboard may be unavailable */
    });
  };

  const iconFill = isDark ? "rgba(255,255,255,0.55)" : "rgba(0,0,0,0.45)";
  const footerTextColor = isDark ? "rgba(255,255,255,0.45)" : "rgba(0,0,0,0.35)";
  const borderColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
  const bgColor = isDark ? "var(--ds-bg-code)" : "var(--ds-bg-code, var(--aion-bg-2))";

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", minWidth: 0, maxWidth: "100%", ...codeStyle }}
      className="group"
    >
      <div style={{ backgroundColor: bgColor, borderRadius: "8px", overflow: "hidden" }}>
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "8px 12px",
          }}
        >
          <span style={{ color: footerTextColor, fontSize: "12px", lineHeight: "16px" }}>
            {language.toLocaleLowerCase()}
          </span>
          <div
            className="opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity"
            style={{ display: "flex", alignItems: "center", gap: "8px" }}
          >
            {canCollapse && (
              <span title={expanded ? "收起" : "展开"} style={{ display: "flex" }}>
                {expanded ? (
                  <ChevronUp
                    size={14}
                    color={iconFill}
                    style={{ cursor: "pointer", display: "block" }}
                    onClick={toggleExpanded}
                  />
                ) : (
                  <ChevronDown
                    size={14}
                    color={iconFill}
                    style={{ cursor: "pointer", display: "block" }}
                    onClick={toggleExpanded}
                  />
                )}
              </span>
            )}
            {!hiddenCodeCopyButton && (
              <span title="复制" style={{ display: "flex" }}>
                <Copy
                  size={14}
                  color={iconFill}
                  style={{ cursor: "pointer", display: "block" }}
                  onClick={handleCopy}
                />
              </span>
            )}
          </div>
        </div>

        {/* Code content — always full content, clipped by maxHeight when collapsed */}
        <div
          style={{
            maxHeight: canCollapse && !expanded ? `${COLLAPSED_HEIGHT}px` : "none",
            overflowY: "hidden",
            overflowX: "visible",
          }}
        >
          <SyntaxHighlighter
            children={formattedContent}
            language={language}
            style={codeTheme}
            PreTag="div"
            wrapLines={isDiff}
            lineProps={
              isDiff
                ? (lineNumber: number) => ({
                    style: {
                      display: "block",
                      ...getDiffLineStyle(diffLines[lineNumber - 1] || "", isDark),
                    },
                  })
                : undefined
            }
            customStyle={{
              margin: 0,
              padding: "0 12px 8px",
              borderRadius: 0,
              border: "none",
              background: "transparent",
              color: "var(--aion-text-primary)",
              overflowX: "auto",
              maxWidth: "100%",
            }}
            codeTagProps={{
              style: {
                color: "var(--aion-text-primary)",
                background: "transparent",
              },
            }}
          />
        </div>

        {/* Footer */}
        {canCollapse && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              padding: "6px 12px",
              cursor: "pointer",
              gap: "4px",
              borderTop: `1px solid ${borderColor}`,
            }}
            onClick={toggleExpanded}
          >
            <span style={{ color: footerTextColor, fontSize: "12px" }}>
              {expanded ? "收起" : `查看剩余 ${totalLines - PREVIEW_LINES} 行`}
            </span>
            {expanded ? (
              <ChevronUp size={12} color={footerTextColor} />
            ) : (
              <ChevronDown size={12} color={footerTextColor} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default CodeBlock;
