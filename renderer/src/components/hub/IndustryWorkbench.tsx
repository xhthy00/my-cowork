import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Boxes, FileArchive, RefreshCw, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";

type InstalledApp = Awaited<ReturnType<typeof window.api.industryList>>["apps"][number];
type Inspection = Awaited<ReturnType<typeof window.api.industryInspect>>;

const CHANNEL = "mycowork-app/v1";

export default function IndustryWorkbench() {
  const [apps, setApps] = useState<InstalledApp[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [pending, setPending] = useState<{ filePath: string; details: Inspection } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [frameRevision, setFrameRevision] = useState(0);
  const [bridgeToken] = useState(() => {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  });
  const frameRef = useRef<HTMLIFrameElement>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await window.api.industryList();
      setApps(result.apps);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  useEffect(() => {
    void refresh();
    return window.api.onBackendReady?.(() => {
      setNotice("");
      void refresh();
    });
  }, [refresh]);

  const active = apps.find((entry) => entry.id === activeId);
  const visibleAppId = active?.id;
  const frameSrc = active?.status === "ready"
    ? "mycowork-app://" + active.id + "/index.html?bridge=" + bridgeToken
    : null;

  const sendAppearance = useCallback(() => {
    if (!frameSrc || !visibleAppId) return;
    const root = document.documentElement;
    const parsedScale = Number.parseFloat(getComputedStyle(root).getPropertyValue("--ui-font-scale"));
    frameRef.current?.contentWindow?.postMessage({
      channel: CHANNEL,
      appId: visibleAppId,
      bridgeToken,
      type: "host.appearance",
      theme: root.classList.contains("dark") || root.getAttribute("data-theme") === "dark" ? "dark" : "light",
      fontScale: Number.isFinite(parsedScale) && parsedScale >= 0.75 && parsedScale <= 1.5 ? parsedScale : 1,
    }, "mycowork-app://" + visibleAppId);
  }, [visibleAppId, bridgeToken, frameSrc]);

  useEffect(() => {
    if (!frameSrc) return;
    const observer = new MutationObserver(sendAppearance);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "style"],
    });
    return () => observer.disconnect();
  }, [frameSrc, sendAppearance]);

  useEffect(() => {
    if (!frameSrc || !active) return;
    const appOrigin = "mycowork-app://" + active.id;
    const onMessage = async (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.origin !== appOrigin) return;
      const message = event.data;
      if (!message || typeof message !== "object" || message.channel !== CHANNEL) return;
      if (message.bridgeToken !== bridgeToken) return;
      if (message.appId !== active.id || message.type !== "request" || typeof message.id !== "string") return;
      const reply = (payload: Record<string, unknown>) => {
        (event.source as Window).postMessage({
          channel: CHANNEL,
          appId: active.id,
          bridgeToken,
          id: message.id,
          type: "response",
          ...payload,
        }, event.origin);
      };
      if (message.operation !== "app.request") {
        reply({ ok: false, error: "unsupported operation" });
        return;
      }
      try {
        if (typeof message.method !== "string" || typeof message.path !== "string") {
          throw new Error("invalid request");
        }
        const data = await window.api.industryRequest(active.id, message.method, message.path, message.body);
        reply({ ok: true, data });
      } catch (cause) {
        reply({ ok: false, error: cause instanceof Error ? cause.message : String(cause) });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [active, bridgeToken, frameSrc]);

  async function choosePackage() {
    setError("");
    setNotice("");
    const picked = await window.api.selectFile?.({ title: "选择行业应用 ZIP" });
    const filePath = picked?.files?.[0]?.filePath;
    if (!filePath) return;
    setBusy(true);
    try {
      const details = await window.api.industryInspect(filePath);
      setPending({ filePath, details });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function installPackage() {
    if (!pending) return;
    setBusy(true);
    try {
      await window.api.industryInstall(pending.filePath, pending.details.sha256);
      setNotice("应用已安装。打开应用后重启后端即可启用。");
      setPending(null);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function restartBackend() {
    setBusy(true);
    try {
      await window.api.restartBackend();
      await refresh();
      setNotice("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function manageApp(appId: string, action: "disable" | "enable" | "rollback") {
    setBusy(true);
    try {
      await window.api.industryManage(appId, action);
      setNotice(action === "rollback" ? "已选择上一版本，重启后端后生效。" : "应用状态已更新，重启后端后生效。");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  if (active) {
    return (
      <section className="flex min-h-[680px] w-full flex-col bg-ds-bg-neutral-default-default">
        <div className="flex min-h-12 flex-wrap items-center justify-between gap-3 border-b border-ds-border-neutral-subtle-default px-4 py-2">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => { setActiveId(null); setLoaded(false); }}>
              <ArrowLeft className="size-4" /> 工作台
            </Button>
            <div>
              <h2 className="m-0 text-sm font-semibold">{active.manifest.name}</h2>
              <p className="m-0 text-[11px] text-ds-text-neutral-muted-default">版本 {active.version}</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => { setLoaded(false); setFrameRevision((value) => value + 1); }}>
            <RefreshCw className="size-4" /> 刷新页面
          </Button>
        </div>
        {error && <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</div>}
        {notice && <div role="status" className="rounded-xl bg-green-50 p-4 text-sm text-green-800">{notice}</div>}
        {active.status === "ready" && frameSrc ? (
          <div className="relative min-h-[560px] flex-1 overflow-hidden bg-ds-bg-neutral-default-default">
            {!loaded && <div className="absolute inset-0 flex items-center justify-center text-sm text-ds-text-neutral-muted-default">正在加载应用…</div>}
            <iframe
              key={frameRevision}
              ref={frameRef}
              src={frameSrc}
              title={active.manifest.name}
              sandbox="allow-scripts allow-same-origin"
              referrerPolicy="no-referrer"
              className="relative h-[calc(100vh-170px)] min-h-[560px] w-full border-0"
              onLoad={() => { setLoaded(true); sendAppearance(); }}
            />
          </div>
        ) : (
          <div className="rounded-2xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-6">
            <p className="m-0 font-medium">应用状态：{active.status}</p>
            {active.error && <p className="mt-2 text-sm text-ds-text-error-default-default">{active.error}</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              {active.status === "pending_restart" && (
                <Button variant="primary" disabled={busy} onClick={() => void restartBackend()}>
                  重启后端以应用变更
                </Button>
              )}
              {active.status === "load_failed" && active.previous_version && (
                <Button variant="outline" disabled={busy} onClick={() => void manageApp(active.id, "rollback")}>
                  回退到 {active.previous_version}
                </Button>
              )}
              {!active.enabled && (
                <Button variant="outline" disabled={busy} onClick={() => void manageApp(active.id, "enable")}>
                  重新启用
                </Button>
              )}
              {active.enabled && active.status === "load_failed" && (
                <Button variant="outline" disabled={busy} onClick={() => void manageApp(active.id, "disable")}>
                  停用应用
                </Button>
              )}
            </div>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="w-full px-6 pb-16 pt-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="m-0 text-2xl font-bold">行业工作台</h2>
          <p className="mt-2 text-sm text-ds-text-neutral-muted-default">
            安装可信的本地应用，集中处理行业业务。
          </p>
        </div>
        <Button variant="primary" disabled={busy} onClick={() => void choosePackage()}>
          <Upload className="size-4" /> 安装 ZIP
        </Button>
      </div>

      {error && <div role="alert" className="mb-4 rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {notice && <div role="status" className="mb-4 rounded-xl bg-green-50 p-4 text-sm text-green-800">{notice}</div>}

      {pending && (
        <div className="mb-6 rounded-2xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-5">
          <div className="flex items-start gap-3">
            <FileArchive className="mt-1 size-5 shrink-0" />
            <div className="min-w-0">
              <h3 className="m-0 text-base font-semibold">{pending.details.manifest.name} · {pending.details.manifest.version}</h3>
              <p className="mt-1 text-sm text-ds-text-neutral-muted-default">{pending.details.manifest.description}</p>
              <p className="mt-3 text-sm">此 ZIP 含可在 MyCowork 后端进程中运行的 Python 代码。请仅安装你信任的来源。</p>
              <p className="mt-2 text-xs text-ds-text-neutral-muted-default">应用 ID：{pending.details.manifest.id} · {pending.details.file_count} 个文件</p>
              {(pending.details.manifest.agent_tools?.length ?? 0) > 0 && (
                <div className="mt-3 rounded-lg border border-ds-border-neutral-subtle-default p-3 text-xs">
                  <p className="m-0 font-medium">将提供给聊天 Agent 的行业工作台工具</p>
                  <ul className="mb-0 mt-2 grid gap-1.5 pl-4">
                    {pending.details.manifest.agent_tools?.map((tool) => (
                      <li key={tool.name}>{tool.title} <span className="text-ds-text-neutral-muted-default">· {tool.access === "write" ? "写入，调用时需确认" : "只读"}</span></li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="mt-4 flex gap-2">
                <Button variant="primary" disabled={busy} onClick={() => void installPackage()}>确认安装</Button>
                <Button variant="outline" disabled={busy} onClick={() => setPending(null)}>取消</Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {apps.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {apps.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => { setActiveId(entry.id); setLoaded(false); }}
              className="flex min-h-36 flex-col items-start rounded-2xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-5 text-left transition-colors hover:bg-ds-bg-neutral-subtle-default focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              <Boxes className="mb-3 size-5 text-ds-text-brand-default-default" />
              <span className="font-semibold">{entry.manifest.name}</span>
              <span className="mt-1 line-clamp-2 text-sm text-ds-text-neutral-muted-default">{entry.manifest.description}</span>
              <span className="mt-auto pt-3 text-xs text-ds-text-neutral-muted-default">{entry.version} · {entry.status}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="flex min-h-60 flex-col items-center justify-center rounded-2xl border border-dashed border-ds-border-neutral-subtle-default text-center">
          <Boxes className="mb-3 size-8 text-ds-text-neutral-muted-default" />
          <p className="m-0 font-medium">还没有安装行业应用</p>
          <p className="mt-2 text-sm text-ds-text-neutral-muted-default">从可信开发者获取 ZIP 后，在这里安装。</p>
        </div>
      )}
    </section>
  );
}
