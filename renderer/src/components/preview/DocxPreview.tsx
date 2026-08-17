/**
 * High-fidelity DOCX preview via docx-preview (read-only).
 */
import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { renderAsync } from "docx-preview";

import { Button } from "@/components/ui/button";

export default function DocxPreview({ path }: { path: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const styleRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    const styleContainer = styleRef.current;
    if (!container) return;

    container.innerHTML = "";
    if (styleContainer) styleContainer.innerHTML = "";
    setLoading(true);
    setError("");

    void (async () => {
      try {
        if (!window.api.readFileBuffer) {
          throw new Error("readFileBuffer 不可用（请重启 Electron）");
        }
        const res = await window.api.readFileBuffer(path);
        if (!res.ok || !res.data) {
          throw new Error(res.error || "读取文件失败");
        }
        if (cancelled || !containerRef.current) return;
        await renderAsync(res.data, containerRef.current, styleRef.current || undefined, {
          className: "docx-preview-body",
          inWrapper: true,
          ignoreWidth: false,
          breakPages: true,
          useBase64URL: true,
        });
        if (!cancelled) setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (containerRef.current) containerRef.current.innerHTML = "";
      if (styleRef.current) styleRef.current.innerHTML = "";
    };
  }, [path]);

  return (
    <div className="relative flex h-full min-h-0 flex-1 flex-col">
      <div ref={styleRef} className="hidden" aria-hidden />
      {loading ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 bg-ds-bg-neutral-default-default/80 text-ds-text-neutral-muted-default">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-body-sm">加载 Word 预览…</span>
        </div>
      ) : null}
      {error ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
          <p className="text-body-sm text-ds-text-error-default-default">{error}</p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void window.api.ipcOpenPath(path)}
          >
            在系统中打开
          </Button>
        </div>
      ) : (
        <div
          ref={containerRef}
          className="docx-preview-scroll h-full min-h-0 flex-1 overflow-auto bg-[#f3f3f3] px-3 py-4"
        />
      )}
    </div>
  );
}
