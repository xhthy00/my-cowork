/**
 * Adapted from eigent: Folder/FilePreview + FileViewerPanel type routing.
 * Session Preview file surface — md / pdf / office / media / text.
 * docx → DocxPreview; xlsx/csv → SpreadsheetEditor; pptx/doc → HTML fallback.
 */
import { CodeXml, Download, FileText, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import DocxPreview from "./DocxPreview";
import OfficeHtmlPreview from "./OfficeHtmlPreview";
import OfficeWatchPreview from "./OfficeWatchPreview";
import SpreadsheetEditor from "./SpreadsheetEditor";
import {
  markdownComponents,
  normalizeMarkdownTables,
} from "@/components/chat/MessageContent";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fileNameFromPath } from "@/lib/userAttachments";
import { fileBasename, normalizeFsPath } from "@/lib/fsPath";
import { toFileUrl } from "@/store/preview";

const IMAGE_EXT = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"]);
const AUDIO_EXT = new Set(["mp3", "wav", "ogg", "m4a", "flac"]);
const VIDEO_EXT = new Set(["mp4", "webm", "mov", "mkv"]);
/** pptx / legacy doc still use openFile → HTML when officecli watch unavailable. */
const OFFICE_HTML_EXT = new Set(["doc", "pptx"]);
const OFFICE_WATCH_EXT = new Set([
  "pptx",
  "ppt",
  "docx",
  "doc",
  "xlsx",
  "xls",
]);

export function extOf(pathOrName: string): string {
  const base = fileBasename(pathOrName) || pathOrName;
  const i = base.lastIndexOf(".");
  return i >= 0 ? base.slice(i + 1).toLowerCase() : "";
}

type Loaded = {
  path: string;
  name: string;
  type: string;
  content?: string;
};

function PreviewShell({
  name,
  path,
  embedded,
  children,
  extraActions,
}: {
  name: string;
  path: string;
  embedded: boolean;
  children: React.ReactNode;
  extraActions?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col bg-ds-bg-neutral-default-default",
        !embedded && "m-2 overflow-hidden rounded-xl",
      )}
    >
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-ds-border-neutral-subtle-default px-3">
        <FileText className="h-4 w-4 shrink-0 text-ds-icon-neutral-muted-default" />
        <span className="min-w-0 flex-1 truncate text-body-sm font-medium text-ds-text-neutral-default-default">
          {name}
        </span>
        {extraActions}
        <Button
          size="icon"
          variant="ghost"
          title="在系统中打开"
          onClick={() => void window.api.ipcOpenPath(path)}
        >
          <Download className="h-4 w-4" />
        </Button>
      </div>
      <div className="relative min-h-0 flex-1">{children}</div>
    </div>
  );
}

export default function FilePreview({
  path,
  title,
  embedded = true,
  tabId,
}: {
  path: string;
  title?: string;
  embedded?: boolean;
  tabId?: string;
}) {
  // Guard against multi-line path blobs and literal \uXXXX escapes.
  const safePath = useMemo(() => normalizeFsPath(path) || path.trim(), [path]);
  const name =
    (title && !/^u[0-9a-fA-F]{4}\./i.test(title) ? title : null) ||
    fileNameFromPath(safePath) ||
    fileBasename(safePath);
  const type = extOf(safePath) || extOf(name);

  if (OFFICE_WATCH_EXT.has(type)) {
    return (
      <OfficeWatchOrFallback
        name={name}
        path={safePath}
        embedded={embedded}
        type={type}
        tabId={tabId}
      />
    );
  }

  if (type === "csv") {
    return (
      <PreviewShell name={name} path={safePath} embedded={embedded}>
        <SpreadsheetEditor path={safePath} ext={type} tabId={tabId} />
      </PreviewShell>
    );
  }

  return (
    <FilePreviewLegacy
      safePath={safePath}
      name={name}
      type={type}
      embedded={embedded}
    />
  );
}

function OfficeWatchOrFallback({
  name,
  path,
  embedded,
  type,
  tabId,
}: {
  name: string;
  path: string;
  embedded: boolean;
  type: string;
  tabId?: string;
}) {
  const [fallback, setFallback] = useState(false);
  if (!fallback) {
    return (
      <PreviewShell name={name} path={path} embedded={embedded}>
        <OfficeWatchPreview path={path} onFallback={() => setFallback(true)} />
      </PreviewShell>
    );
  }
  if (type === "docx") {
    return (
      <PreviewShell name={name} path={path} embedded={embedded}>
        <DocxPreview path={path} />
      </PreviewShell>
    );
  }
  if (type === "xlsx" || type === "xls") {
    return (
      <PreviewShell name={name} path={path} embedded={embedded}>
        <SpreadsheetEditor path={path} ext="xlsx" tabId={tabId} />
      </PreviewShell>
    );
  }
  return (
    <FilePreviewLegacy
      safePath={path}
      name={name}
      type={type}
      embedded={embedded}
    />
  );
}

/** Non-docx/xlsx/csv preview path (hooks isolated from early returns above). */
function FilePreviewLegacy({
  safePath,
  name,
  type,
  embedded,
}: {
  safePath: string;
  name: string;
  type: string;
  embedded: boolean;
}) {
  const [file, setFile] = useState<Loaded | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showSource, setShowSource] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setShowSource(false);
    try {
      if (type === "zip") {
        setFile({ path: safePath, name, type });
        return;
      }
      if (IMAGE_EXT.has(type) || AUDIO_EXT.has(type) || VIDEO_EXT.has(type)) {
        if (window.api.readFileDataUrl) {
          const dataUrl = await window.api.readFileDataUrl(safePath);
          setFile({ path: safePath, name, type, content: dataUrl });
        } else {
          setFile({ path: safePath, name, type, content: toFileUrl(safePath) });
        }
        return;
      }
      if (type === "pdf") {
        if (!window.api.readFileDataUrl) {
          setFile({ path: safePath, name, type, content: toFileUrl(safePath) });
          return;
        }
        const dataUrl = await window.api.readFileDataUrl(safePath);
        setFile({ path: safePath, name, type, content: dataUrl });
        return;
      }
      if (!window.api.openFile) {
        if (window.api.readTextFile) {
          const r = await window.api.readTextFile(safePath);
          if (r.error) throw new Error(r.error);
          setFile({ path: safePath, name, type, content: r.content ?? "" });
          return;
        }
        throw new Error("openFile 不可用（请重启 Electron）");
      }
      const content = await window.api.openFile(type, safePath, false);
      setFile({ path: safePath, name, type, content });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setFile({ path: safePath, name, type });
    } finally {
      setLoading(false);
    }
  }, [safePath, name, type]);

  useEffect(() => {
    void load();
  }, [load]);

  const canToggleSource = type === "md" || type === "html" || type === "htm";

  const body = useMemo(() => {
    if (!file) return null;
    if (file.type === "zip") {
      return (
        <div className="flex h-full items-center justify-center text-body-sm text-ds-text-neutral-muted-default">
          ZIP 预览不受支持
        </div>
      );
    }
    if (IMAGE_EXT.has(file.type)) {
      if (!file.content) {
        return (
          <div className="flex h-full items-center justify-center p-4 text-body-sm text-ds-text-error-default-default">
            无法加载图片
          </div>
        );
      }
      return (
        <div className="flex h-full items-center justify-center overflow-auto p-4">
          <img
            src={file.content}
            alt={file.name}
            className="max-h-full max-w-full object-contain"
          />
        </div>
      );
    }
    if (AUDIO_EXT.has(file.type)) {
      return (
        <div className="flex h-full items-center justify-center p-6">
          <audio
            controls
            src={file.content || toFileUrl(file.path)}
            className="w-full max-w-md"
          />
        </div>
      );
    }
    if (VIDEO_EXT.has(file.type)) {
      return (
        <div className="flex h-full items-center justify-center p-4">
          <video
            controls
            src={file.content || toFileUrl(file.path)}
            className="max-h-full max-w-full"
          />
        </div>
      );
    }
    if (file.type === "pdf") {
      return (
        <iframe
          title={file.name}
          src={file.content}
          className="h-full w-full flex-1 border-0 bg-ds-bg-neutral-subtle-default"
        />
      );
    }
    if (OFFICE_HTML_EXT.has(file.type) && !showSource) {
      return (
        <div className="flex h-full min-h-0 flex-1 flex-col">
          {file.type === "doc" ? (
            <p className="shrink-0 border-b border-ds-border-neutral-subtle-default px-3 py-1 text-[11px] text-ds-text-neutral-muted-default">
              旧版 .doc 为简化 HTML 预览；建议另存为 .docx 以获得更好预览效果。
            </p>
          ) : null}
          <OfficeHtmlPreview content={file.content} />
        </div>
      );
    }
    if (file.type === "md" && !showSource) {
      return (
        <div className="markdown-body h-full overflow-auto px-4 py-3 font-['Inter'] text-[14px] leading-[1.65] text-ds-text-neutral-default-default [&_a]:underline [&_code]:rounded [&_code]:bg-ds-bg-neutral-subtle-default [&_code]:px-1 [&_code]:text-[12px] [&_h1]:mb-2 [&_h1]:mt-4 [&_h1]:text-[18px] [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-[16px] [&_h2]:font-bold [&_h3]:mb-1.5 [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:my-0.5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-ds-bg-neutral-subtle-default [&_pre]:p-3 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {normalizeMarkdownTables(file.content || "")}
          </ReactMarkdown>
        </div>
      );
    }
    if ((file.type === "html" || file.type === "htm") && !showSource) {
      return <OfficeHtmlPreview content={file.content} />;
    }
    return (
      <pre className="h-full overflow-auto whitespace-pre-wrap bg-ds-bg-neutral-subtle-default p-3 font-mono text-xs text-ds-text-neutral-default-default">
        {file.content ?? ""}
      </pre>
    );
  }, [file, showSource]);

  return (
    <PreviewShell
      name={name}
      path={safePath}
      embedded={embedded}
      extraActions={
        canToggleSource ? (
          <Button
            size="icon"
            variant={showSource ? "secondary" : "ghost"}
            title="源码 / 渲染"
            onClick={() => setShowSource((v) => !v)}
          >
            <CodeXml className="h-4 w-4" />
          </Button>
        ) : null
      }
    >
      {loading ? (
        <div className="flex h-full items-center justify-center gap-2 text-ds-text-neutral-muted-default">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-body-sm">加载中…</span>
        </div>
      ) : error ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
          <p className="text-body-sm text-ds-text-error-default-default">{error}</p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void window.api.ipcOpenPath(safePath)}
          >
            在系统中打开
          </Button>
        </div>
      ) : (
        body
      )}
    </PreviewShell>
  );
}
