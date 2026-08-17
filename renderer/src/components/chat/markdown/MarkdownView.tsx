/**
 * Ported from AionUi (packages/desktop/src/renderer/components/Markdown/index.tsx).
 * Apache-2.0 © AionUi — ShadowView replaced with the `.aion-md` stylesheet
 * (styles/markdown.css) since my-cowork has no custom-theme injection; the
 * rendered typography matches AionUi's markdown-shadow-body exactly.
 */
import "katex/dist/katex.min.css";

import { useCallback, useMemo } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { fileBasename } from "@/lib/fsPath";
import { usePageTabStore } from "@/store/pageTab";
import { usePreviewStore } from "@/store/preview";
import { cn } from "@/lib/utils";

import CodeBlock from "./CodeBlock";
import {
  convertLatexDelimiters,
  resolveLocalFileLinkPath,
  resolveLocalFileLinkReference,
  type LocalFileLinkReference,
} from "./markdownUtils";

const REMARK_PLUGINS = [remarkGfm, remarkMath, remarkBreaks];

const isLocalFilePath = (src: string): boolean => {
  if (src.startsWith("http://") || src.startsWith("https://")) return false;
  if (src.startsWith("data:")) return false;
  return true;
};

/** Open a local deliverable in the preview panel (my-cowork counterpart of AionUi useLocalFilePreview). */
function openLocalFile(path: string) {
  usePageTabStore.getState().openPreviewFoldSide();
  usePreviewStore.getState().openFile(path, fileBasename(path) || path);
}

function LocalFileLink({
  reference,
  children,
}: {
  reference: LocalFileLinkReference;
  children?: React.ReactNode;
}) {
  const label = children ?? reference.rawReference;
  const name = fileBasename(reference.filePath) || reference.filePath;
  return (
    <button
      type="button"
      className="aion-md-local-file-link"
      title={reference.rawReference}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        openLocalFile(reference.filePath);
      }}
    >
      <span className="truncate">{label}</span>
      <span className="aion-md-local-file-line">{name}</span>
    </button>
  );
}

type MarkdownViewProps = {
  children: string;
  hiddenCodeCopyButton?: boolean;
  codeStyle?: React.CSSProperties;
  className?: string;
};

const MarkdownView: React.FC<MarkdownViewProps> = ({
  hiddenCodeCopyButton,
  codeStyle,
  className,
  children: childrenProp,
}) => {
  const normalizedChildren = useMemo(() => {
    if (typeof childrenProp === "string") {
      let text = childrenProp.replace(/file:\/\//g, "");
      text = convertLatexDelimiters(text);
      return text;
    }
    return childrenProp;
  }, [childrenProp]);

  const handleLinkClick = useCallback((e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const href = (e.currentTarget as HTMLAnchorElement).href;
    if (!href) return;
    window.open(href, "_blank", "noopener,noreferrer");
  }, []);

  // Memoize components so React preserves component identity across re-renders.
  // Without this, every streaming update creates new function references → React
  // unmounts/remounts all custom components → hooks & DOM state are lost.
  const components = useMemo<Components>(
    () => ({
      code(props) {
        const { node: _node, ...rest } = props;
        return (
          <CodeBlock
            {...(rest as unknown as Parameters<typeof CodeBlock>[0])}
            codeStyle={codeStyle}
            hiddenCodeCopyButton={hiddenCodeCopyButton}
          />
        );
      },
      a({ node: _node, ...anchorProps }) {
        const rawHref = typeof anchorProps.href === "string" ? anchorProps.href : "";
        const localFileReference = resolveLocalFileLinkReference(rawHref);
        if (localFileReference) {
          return (
            <LocalFileLink reference={localFileReference}>{anchorProps.children}</LocalFileLink>
          );
        }
        return (
          <a {...anchorProps} target="_blank" rel="noreferrer" onClick={handleLinkClick} />
        );
      },
      img({ node: _node, ...imgProps }) {
        const src = imgProps.src || "";
        if (isLocalFilePath(src)) {
          // Local image: click opens the preview panel instead of a broken img.
          return (
            <img
              {...imgProps}
              alt={imgProps.alt || ""}
              style={{ cursor: "pointer", ...(imgProps.style || {}) }}
              onClick={() => openLocalFile(decodeURIComponent(src))}
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = "none";
              }}
            />
          );
        }
        return <img {...imgProps} alt={imgProps.alt || ""} />;
      },
    }),
    [codeStyle, hiddenCodeCopyButton, handleLinkClick],
  );

  return (
    <div className={cn("aion-md relative w-full min-w-0", className)}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={[rehypeKatex]}
        components={components}
        urlTransform={(url) => (resolveLocalFileLinkPath(url) ? url : defaultUrlTransform(url))}
      >
        {normalizedChildren}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownView;
