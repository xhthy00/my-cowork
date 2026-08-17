/**
 * OfficeCLI watch preview — adapted from AionUi OfficeWatchViewer (simplified).
 * Electron uses <webview> (bypasses parent CSP); browser falls back to <iframe>.
 */
import { Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

type Status = "starting" | "installing" | "ready" | "error";

function previewKind(path: string): "ppt" | "word" | "excel" {
  const lower = path.toLowerCase();
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls") || lower.endsWith(".csv")) {
    return "excel";
  }
  if (lower.endsWith(".docx") || lower.endsWith(".doc")) {
    return "word";
  }
  return "ppt";
}

function isElectronApp(): boolean {
  return navigator.userAgent.includes("Electron");
}

function OfficeWatchFrame({ url }: { url: string }) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    if (isElectronApp()) {
      const el = document.createElement("webview");
      el.setAttribute("src", url);
      el.setAttribute("partition", "persist:office-watch-preview");
      el.setAttribute(
        "webpreferences",
        "webSecurity=no, allowRunningInsecureContent",
      );
      el.style.width = "100%";
      el.style.height = "100%";
      el.style.border = "none";
      el.style.display = "flex";
      host.replaceChildren(el);
      return () => {
        host.replaceChildren();
      };
    }

    const iframe = document.createElement("iframe");
    iframe.title = "Office preview";
    iframe.src = url;
    iframe.className = "h-full w-full border-0 bg-white";
    iframe.setAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-forms allow-popups",
    );
    iframe.style.width = "100%";
    iframe.style.height = "100%";
    iframe.style.border = "0";
    host.replaceChildren(iframe);
    return () => {
      host.replaceChildren();
    };
  }, [url]);

  return <div ref={hostRef} className="h-full w-full min-h-0" />;
}

export default function OfficeWatchPreview({
  path,
  onFallback,
}: {
  path: string;
  onFallback?: () => void;
}) {
  const [status, setStatus] = useState<Status>("starting");
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);

  const start = useCallback(async () => {
    setStatus("starting");
    setError("");
    setUrl(null);
    try {
      const backendUrl = await window.api.getBackendUrl();
      if (!backendUrl) throw new Error("后端未连接");

      const st = await fetch(`${backendUrl}/api/officecli/status`).then((r) =>
        r.json(),
      );
      if (st.status !== "ready") {
        setStatus("installing");
        const installed = await fetch(`${backendUrl}/api/officecli/install`, {
          method: "POST",
        }).then((r) => r.json());
        if (installed.status !== "ready") {
          throw new Error(
            installed.detail ||
              installed.error_code ||
              "OfficeCLI 安装失败，请手动安装后重试",
          );
        }
      }

      const kind = previewKind(path);
      // Brief delay so the file is fully flushed to disk.
      await new Promise((r) => setTimeout(r, 800));
      const res = await fetch(`${backendUrl}/api/${kind}-preview/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: path }),
      }).then((r) => r.json());
      if (res.status !== "ready" || !res.url) {
        throw new Error(res.detail || res.error_code || "预览启动失败");
      }
      setUrl(res.url as string);
      setStatus("ready");
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [path]);

  useEffect(() => {
    void start();
    return () => {
      void (async () => {
        try {
          const backendUrl = await window.api.getBackendUrl();
          if (!backendUrl) return;
          const kind = previewKind(path);
          await fetch(`${backendUrl}/api/${kind}-preview/stop`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_path: path }),
          });
        } catch {
          /* ignore */
        }
      })();
    };
  }, [path, retryKey, start]);

  if (status === "ready" && url) {
    return <OfficeWatchFrame url={url} />;
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-sm text-ds-text-neutral-muted-default">
      {(status === "starting" || status === "installing") && (
        <>
          <Loader2 className="h-6 w-6 animate-spin" />
          <div>
            {status === "installing"
              ? "正在安装 OfficeCLI…"
              : "正在启动预览…"}
          </div>
        </>
      )}
      {status === "error" && (
        <>
          <div className="max-w-md text-center text-ds-text-neutral-default-default">
            {error}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setRetryKey((k) => k + 1)}
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" />
              重试
            </Button>
            {onFallback && (
              <Button size="sm" variant="ghost" onClick={onFallback}>
                使用简易预览
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
