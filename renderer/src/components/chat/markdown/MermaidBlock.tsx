/**
 * Ported from AionUi (packages/desktop/src/renderer/components/Markdown/MermaidBlock.tsx).
 * Apache-2.0 © AionUi — arco/icon-park/i18n swapped for lucide + zh-CN labels.
 */
import { Copy } from "lucide-react";
import mermaid from "mermaid";
import React, { useEffect, useRef, useState } from "react";
import SyntaxHighlighter from "react-syntax-highlighter";
import { vs, vs2015 } from "react-syntax-highlighter/dist/esm/styles/hljs";

type MermaidBlockProps = {
  code: string;
  style?: React.CSSProperties;
};

let initializedTheme: "light" | "dark" | null = null;
const ensureMermaidInitialized = (theme: "light" | "dark") => {
  if (initializedTheme === theme) return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    suppressErrorRendering: true,
    theme: theme === "dark" ? "dark" : "default",
    fontFamily: "inherit",
  });
  initializedTheme = theme;
};

const withResponsiveSvg = (svg: string): string => {
  return svg.replace(/<svg\b([^>]*)>/i, (_match, attrs: string) => {
    if (/style\s*=/.test(attrs)) {
      return `<svg${attrs.replace(
        /style\s*=\s*(["'])(.*?)\1/i,
        (_styleMatch: string, quote: string, styleValue: string) =>
          ` style=${quote}${styleValue};max-width: 100%; height: auto; display: block;${quote}`,
      )}>`;
    }
    return `<svg${attrs} style="max-width: 100%; height: auto; display: block;">`;
  });
};

function MermaidBlock({ code, style }: MermaidBlockProps) {
  const blockIdRef = useRef(`mermaid-${Math.random().toString(36).slice(2, 10)}`);
  const preferredViewModeRef = useRef<"preview" | "source" | null>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [viewMode, setViewMode] = useState<"preview" | "source">("source");
  const [debouncedCode, setDebouncedCode] = useState(code);
  const [currentTheme, setCurrentTheme] = useState<"light" | "dark">(() => {
    return (document.documentElement.getAttribute("data-theme") as "light" | "dark") || "light";
  });

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedCode(code), 300);
    return () => clearTimeout(timer);
  }, [code]);

  useEffect(() => {
    const updateTheme = () => {
      const theme = (document.documentElement.getAttribute("data-theme") as "light" | "dark") || "light";
      setCurrentTheme(theme);
    };
    const observer = new MutationObserver(updateTheme);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    const source = debouncedCode.trim();

    if (!source) {
      setSvg(null);
      setIsRendering(false);
      setViewMode("source");
      return () => {
        cancelled = true;
      };
    }

    setSvg(null);
    setIsRendering(true);

    const renderDiagram = async () => {
      try {
        ensureMermaidInitialized(currentTheme);
        const { svg: renderedSvg } = await mermaid.render(`${blockIdRef.current}-${Date.now()}`, source);
        if (!cancelled) {
          setSvg(withResponsiveSvg(renderedSvg));
          setIsRendering(false);
          setViewMode(preferredViewModeRef.current === "source" ? "source" : "preview");
        }
      } catch {
        if (!cancelled) {
          setSvg(null);
          setIsRendering(false);
          setViewMode("source");
        }
      }
    };

    void renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [debouncedCode, currentTheme]);

  const codeTheme = currentTheme === "dark" ? vs2015 : vs;
  const shouldShowLoading = isRendering && preferredViewModeRef.current !== "source";

  return (
    <div style={{ width: "100%", minWidth: 0, maxWidth: "100%", ...style }}>
      <div
        style={{
          border: "1px solid var(--aion-bg-3)",
          borderRadius: "0.3rem",
          overflow: "hidden",
          overflowX: "auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "8px",
            backgroundColor: "var(--aion-bg-2)",
            borderTopLeftRadius: "0.3rem",
            borderTopRightRadius: "0.3rem",
            padding: "6px 10px",
            borderBottom: "1px solid var(--aion-bg-3)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span
              style={{
                textDecoration: "none",
                color: "var(--aion-text-secondary)",
                fontSize: "12px",
                lineHeight: "20px",
              }}
            >
              {"<mermaid>"}
            </span>
            {svg && (
              <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <div
                  style={{
                    cursor: "pointer",
                    color: viewMode === "preview" ? "var(--aion-text-primary)" : "var(--aion-text-secondary)",
                    fontSize: "12px",
                    lineHeight: "20px",
                  }}
                  onMouseDown={(event: React.MouseEvent) => {
                    if (event.button === 0) {
                      event.preventDefault();
                      preferredViewModeRef.current = "preview";
                      setViewMode("preview");
                    }
                  }}
                >
                  预览
                </div>
                <span style={{ color: "var(--aion-text-secondary)", fontSize: "12px", lineHeight: "20px" }}>/</span>
                <div
                  style={{
                    cursor: "pointer",
                    color: viewMode === "source" ? "var(--aion-text-primary)" : "var(--aion-text-secondary)",
                    fontSize: "12px",
                    lineHeight: "20px",
                  }}
                  onMouseDown={(event: React.MouseEvent) => {
                    if (event.button === 0) {
                      event.preventDefault();
                      preferredViewModeRef.current = "source";
                      setViewMode("source");
                    }
                  }}
                >
                  源码
                </div>
              </div>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
            <Copy
              size={16}
              style={{ cursor: "pointer", flexShrink: 0, color: "var(--aion-text-secondary)" }}
              onClick={() => {
                void navigator.clipboard.writeText(code).catch(() => {
                  /* clipboard may be unavailable */
                });
              }}
            />
          </div>
        </div>

        {svg && viewMode === "preview" ? (
          <div
            data-testid="mermaid-diagram"
            style={{
              backgroundColor: "var(--aion-bg-1)",
              padding: "12px",
              overflowX: "auto",
              display: "flex",
              justifyContent: "center",
            }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : shouldShowLoading ? (
          <div
            data-testid="mermaid-loading"
            style={{
              backgroundColor: "var(--aion-bg-1)",
              padding: "16px 12px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              color: "var(--aion-text-secondary)",
              fontSize: "13px",
              lineHeight: "20px",
            }}
          >
            <div
              aria-hidden="true"
              className="aion-md-loading"
              style={{
                width: "12px",
                height: "12px",
                borderRadius: "999px",
                border: "2px solid var(--aion-bg-3)",
                borderTopColor: "var(--aion-text-secondary)",
                flexShrink: 0,
              }}
            />
            <span>加载中…</span>
          </div>
        ) : (
          <SyntaxHighlighter
            children={code}
            language="mermaid"
            style={codeTheme}
            PreTag="div"
            customStyle={{
              margin: 0,
              borderRadius: 0,
              border: "none",
              background: "transparent",
              color: "var(--aion-text-primary)",
              overflowX: "auto",
              maxWidth: "100%",
            }}
            codeTagProps={{ style: { color: "var(--aion-text-primary)" } }}
          />
        )}
      </div>
    </div>
  );
}

export default React.memo(MermaidBlock);
