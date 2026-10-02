import { apiFetch as fetch } from "@/api/backend";
import { useEffect, useState } from "react";
import { Globe, Link2, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { usePageTabStore, type BrowserSection } from "@/store/pageTab";

interface CdpBrowser {
  id: string;
  port: number;
  name?: string;
  isExternal?: boolean;
}

export default function BrowserSettingsPanel() {
  const section = usePageTabStore((s) => s.browserSection);
  const setSection = usePageTabStore((s) => s.setBrowserSection);
  const [browsers, setBrowsers] = useState<CdpBrowser[]>([]);
  const [port, setPort] = useState("9222");
  const [status, setStatus] = useState("");
  const [extEnabled, setExtEnabled] = useState(false);
  const [agentBrowser, setAgentBrowser] = useState<{ open: boolean; status: string; url: string; title: string } | null>(null);
  const [agentImage, setAgentImage] = useState("");
  const [agentError, setAgentError] = useState("");
  const [restartingAgentBackend, setRestartingAgentBackend] = useState(false);

  useEffect(() => {
    if (section !== "agent") return;
    let disposed = false;
    async function refreshAgent() {
      try {
        const backendUrl = await window.api.getBackendUrl();
        if (!backendUrl || disposed) return;
        const stateResponse = await fetch(`${backendUrl}/api/browser/state`);
        if (!stateResponse.ok) {
          if (stateResponse.status === 404) {
            throw new Error("当前运行的后端缺少代理浏览器接口（404）。更新代码后请重启后端；若使用安装包，请更新应用。");
          }
          throw new Error(`浏览器状态读取失败 (${stateResponse.status})`);
        }
        const state = await stateResponse.json() as { open: boolean; status: string; url: string; title: string };
        if (disposed) return;
        setAgentBrowser(state);
        setAgentError("");
        if (!state.open) { setAgentImage(""); return; }
        const screenshotResponse = await fetch(`${backendUrl}/api/browser/screenshot`);
        const shot = await screenshotResponse.json() as { image?: string; error?: string };
        if (!disposed) {
          setAgentImage(shot.image || "");
          setAgentError(shot.error || "");
        }
      } catch (error) {
        if (!disposed) setAgentError(error instanceof Error ? error.message : String(error));
      }
    }
    void refreshAgent();
    const interval = setInterval(() => void refreshAgent(), 4000);
    return () => { disposed = true; clearInterval(interval); };
  }, [section]);

  async function refresh() {
    try {
      const list = await window.api.getCdpBrowsers?.();
      setBrowsers(list || []);
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <Tabs
      value={section}
      onValueChange={(v) => setSection(v as BrowserSection)}
      className="browser-settings-panel flex h-auto w-full min-w-0 flex-col"
    >
      <aside className="browser-settings-nav mb-4 w-full shrink-0">
        <TabsList appearance="ghost" className="w-full flex-row flex-wrap gap-2">
          {(
            [
              ["agent", "代理浏览器"],
              ["cdp", "外部 CDP"],
              ["extension", "插件"],
              ["cookies", "Cookie"],
            ] as const
          ).map(([id, label]) => (
            <TabsTrigger key={id} value={id}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
      </aside>
      <div className="m-auto flex h-auto w-full min-w-0 flex-1 flex-col">
        {section === "agent" && (
          <div className="pb-4">
            <div className="overflow-hidden rounded-2xl bg-ds-bg-neutral-default-default p-5">
              <div className="mb-4 flex items-center gap-3">
                <span className={cn("h-2.5 w-2.5 rounded-full", agentBrowser?.open ? "bg-green-500" : "bg-slate-300")} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{agentBrowser?.title || (agentBrowser?.open ? "浏览器已打开" : "等待代理打开浏览器")}</div>
                  <div className="truncate text-xs text-ds-text-neutral-muted-default">{agentBrowser?.url || "代理使用内置 Playwright Chromium 时，这里会显示当前页面。"}</div>
                </div>
              </div>
              {agentError && <p className="mb-3 text-xs text-ds-text-error-default-default">{agentError}</p>}
              {agentError.includes("缺少代理浏览器接口") && (
                <div className="mb-4 flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={restartingAgentBackend}
                    onClick={async () => {
                      setRestartingAgentBackend(true);
                      try {
                        await window.api.restartBackend?.();
                        setAgentError("");
                      } catch (error) {
                        setAgentError(error instanceof Error ? error.message : "重启后端失败");
                      } finally {
                        setRestartingAgentBackend(false);
                      }
                    }}
                  >
                    {restartingAgentBackend ? "正在重启…" : "重启后端"}
                  </Button>
                  <span className="text-xs text-ds-text-neutral-muted-default">重启会中断正在执行的任务</span>
                </div>
              )}
              {agentImage ? (
                <img src={agentImage} alt="代理浏览器当前页面" className="w-full rounded-xl border border-ds-border-neutral-default-default" />
              ) : (
                <div className="flex min-h-64 items-center justify-center rounded-xl bg-ds-bg-neutral-subtle-default text-sm text-ds-text-neutral-muted-default">
                  {agentBrowser?.open ? "正在获取页面预览…" : "暂无浏览器页面"}
                </div>
              )}
            </div>
          </div>
        )}
        {section === "cdp" && (
          <>
            {/* Adapted from eigent CDP.tsx */}
            <div className="mb-4 flex flex-col gap-4 rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4">
              <div className="flex w-full flex-row flex-wrap items-center justify-between gap-3">
                <div className="text-sm font-bold text-ds-text-neutral-default-default">
                  CDP 浏览器池
                </div>
                <div className="flex flex-row flex-wrap gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={async () => {
                      const r = await window.api.launchCdpBrowser?.();
                      setStatus(r?.error || `已启动端口 ${r?.port ?? "?"}`);
                      await refresh();
                    }}
                  >
                    <Plus className="h-4 w-4" />
                    打开空白浏览器
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      const r = await window.api.connectCdpBrowser?.(Number(port) || 9222);
                      setStatus(r?.error || `已连接 ${port || "9222"}`);
                      await refresh();
                    }}
                  >
                    <Link2 className="h-4 w-4" />
                    连接已有浏览器
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  className="h-8 w-28 rounded-lg border border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default px-3 text-sm outline-none"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  placeholder="端口"
                />
                {status && (
                  <p className="text-xs text-ds-text-neutral-subtle-default">{status}</p>
                )}
              </div>
              <div className="mt-2 flex min-h-[200px] w-full flex-col gap-2">
                {browsers.map((b) => (
                  <div
                    key={b.id}
                    className="flex items-center justify-between rounded-xl bg-ds-bg-neutral-subtle-default px-4 py-2"
                  >
                    <div className="flex items-center gap-3">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-ds-text-success-default-default" />
                      <div>
                        <div className="text-sm font-bold text-ds-text-neutral-default-default">
                          {b.name || `浏览器 :${b.port}`}
                        </div>
                        <div className="font-mono text-xs text-ds-text-neutral-muted-default">
                          端口 {b.port}
                          {b.isExternal ? " · 外部" : ""}
                        </div>
                      </div>
                    </div>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="text-ds-text-error-default-default"
                      onClick={async () => {
                        await window.api.removeCdpBrowser?.(b.id);
                        await refresh();
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
                {!browsers.length && (
                  <div className="flex flex-col items-center justify-center gap-2 px-4 py-8 text-center">
                    <Globe className="h-12 w-12 text-ds-text-neutral-muted-default opacity-50" />
                    <div className="text-sm font-bold text-ds-text-neutral-default-default">
                      浏览器池为空
                    </div>
                    <p className="text-xs text-ds-text-neutral-muted-default">
                      使用上方按钮启动或连接浏览器
                    </p>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
        {section === "extension" && (
          <>
            <div className="mb-4 flex items-center justify-between rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4">
              <div>
                <div className="font-medium">启用扩展助手</div>
                <div className="text-xs text-ds-text-neutral-subtle-default">
                  用于调试页面上下文
                </div>
              </div>
              <Switch checked={extEnabled} onCheckedChange={setExtEnabled} />
            </div>
          </>
        )}
        {section === "cookies" && (
          <>
            <div className="mb-4 rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4 text-sm text-ds-text-neutral-muted-default">
              Cookie 导入/导出占位 — 通过 Electron 分区 `persist:session-preview` 持久化。
            </div>
          </>
        )}
      </div>
    </Tabs>
  );
}
