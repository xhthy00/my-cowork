/**
 * Adapted from eigent: pages/History.tsx
 * Full History shell: welcome headline + HistoryTabsNav + tab bodies.
 */
import { useEffect, useState, type CSSProperties } from "react";
import { Globe, Link2, Plus, Trash2 } from "lucide-react";

import HomeHub from "@/components/hub/HomeHub";
import AssistantsView from "@/components/hub/AssistantsView";
import { HistoryTabsNav } from "@/components/hub/HistoryTabsNav";
import SkillsView from "@/components/skills/SkillsView";
import MemoryView from "@/components/memory/MemoryView";
import Settings from "@/components/settings/Settings";
import McpConnectorsPanel from "@/components/settings/McpConnectorsPanel";
import KnowledgeView from "@/components/knowledge/KnowledgeView";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  usePageTabStore,
  type AgentsSection,
  type BrowserSection,
  type HubTab,
} from "@/store/pageTab";

function timeGreeting(): string {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return "早上好";
  if (hour >= 12 && hour < 17) return "下午好";
  return "晚上好";
}

function AgentsHub() {
  const section = usePageTabStore((s) => s.agentsSection);
  const setSection = usePageTabStore((s) => s.setAgentsSection);
  const items = [
    ["skills", "技能"],
    ["sub-agents", "办公助手"],
    ["memory", "记忆"],
  ] as const;

  return (
    <Tabs
      value={section}
      onValueChange={(v) => setSection(v as AgentsSection)}
      className="flex h-auto w-full"
    >
      {/* Adapted from eigent VerticalNav — ghost tabs: white chip on grey page */}
      <aside className="sticky top-[var(--home-hub-history-tabs-offset,49px)] z-10 flex w-40 shrink-0 grow-0 flex-col self-start pr-6 pt-8">
        <TabsList appearance="ghost" className="w-full">
          {items.map(([id, label]) => (
            <TabsTrigger key={id} value={id}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
      </aside>
      <div className="flex h-auto w-full min-w-0 flex-1 flex-col">
        {section === "skills" && <SkillsView />}
        {section === "memory" && <MemoryView />}
        {section === "sub-agents" && <AssistantsView />}
      </div>
    </Tabs>
  );
}

function ConnectorsHub() {
  return (
    <div className="m-auto flex h-auto w-full flex-1 flex-col">
      <McpConnectorsPanel />
    </div>
  );
}

interface CdpBrowser {
  id: string;
  port: number;
  name?: string;
  isExternal?: boolean;
}

function BrowserHub() {
  const section = usePageTabStore((s) => s.browserSection);
  const setSection = usePageTabStore((s) => s.setBrowserSection);
  const [browsers, setBrowsers] = useState<CdpBrowser[]>([]);
  const [port, setPort] = useState("9222");
  const [status, setStatus] = useState("");
  const [extEnabled, setExtEnabled] = useState(false);

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
      className="flex h-auto w-full"
    >
      <aside className="sticky top-[var(--home-hub-history-tabs-offset,49px)] z-10 flex w-40 shrink-0 grow-0 flex-col self-start pr-6 pt-8">
        <TabsList appearance="ghost" className="w-full">
          {(
            [
              ["cdp", "连接"],
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
        {section === "cdp" && (
          <>
            {/* Adapted from eigent CDP.tsx */}
            <div className="px-6 pb-6 pt-8">
              <div className="text-heading-sm font-bold text-ds-text-neutral-default-default">
                CDP 浏览器连接
              </div>
            </div>
            <div className="mb-8 flex flex-col gap-4 rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4">
              <div className="flex w-full flex-row items-center justify-between gap-3">
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
              <div className="flex items-center gap-2">
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
            <div className="flex w-full items-center justify-between px-6 pb-6 pt-8">
              <div className="text-heading-sm font-bold">插件</div>
            </div>
            <div className="mb-8 flex items-center justify-between rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4">
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
            <div className="flex w-full items-center justify-between px-6 pb-6 pt-8">
              <div className="text-heading-sm font-bold">Cookie</div>
            </div>
            <div className="mb-8 rounded-2xl bg-ds-bg-neutral-default-default px-6 py-4 text-sm text-ds-text-neutral-muted-default">
              Cookie 导入/导出占位 — 通过 Electron 分区 `persist:session-preview` 持久化。
            </div>
          </>
        )}
      </div>
    </Tabs>
  );
}

export default function HubView() {
  const hubTab = usePageTabStore((s) => s.hubTab);
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const [visited, setVisited] = useState<HubTab[]>([hubTab]);

  useEffect(() => {
    setVisited((prev) => (prev.includes(hubTab) ? prev : [...prev, hubTab]));
  }, [hubTab]);

  return (
    <div className="flex h-full w-full flex-1 flex-col px-1 pb-1">
      {/* Grey scroll page — white welcome/nav sit on top */}
      <div className="scrollbar-hide h-full overflow-y-auto rounded-2xl bg-ds-bg-neutral-subtle-default">
        <div className="flex w-full flex-row bg-ds-bg-neutral-default-default px-[var(--hub-gutter)] py-8">
          <p className="m-0 inline-flex flex-wrap items-baseline gap-2">
            <span className="history-welcome-headline text-[32px] font-bold not-italic text-ds-text-brand-muted-default">
              {timeGreeting()}
            </span>
            <span className="history-welcome-headline text-[32px] font-bold not-italic text-ds-text-brand-default-default">
              ！
            </span>
          </p>
        </div>

        {/* Sticky History tabs */}
        <div
          className="sticky -top-px z-20 flex flex-col items-center justify-between border-b border-ds-border-neutral-subtle-disabled bg-ds-bg-neutral-default-default px-[var(--hub-gutter)] pt-2 pb-2"
          style={
            {
              ["--home-hub-history-tabs-offset"]: "49px",
            } as CSSProperties
          }
        >
          <div className="mx-auto flex w-full flex-row items-center">
            <HistoryTabsNav activeTab={hubTab} onChange={setHubTab} />
          </div>
        </div>

        {visited.includes("home") && (
          <div
            className={hubTab === "home" ? "flex h-auto w-full px-[var(--hub-gutter)] pb-[120px]" : "hidden"}
            aria-hidden={hubTab !== "home"}
          >
            <HomeHub />
          </div>
        )}

        <div className="m-auto flex h-auto w-full max-w-[1020px] flex-1 flex-col">
          <div className="flex h-auto w-full px-6 pb-[120px]">
            {visited.includes("agents") && (
              <div className={hubTab === "agents" ? "contents" : "hidden"} aria-hidden={hubTab !== "agents"}>
                <AgentsHub />
              </div>
            )}
            {visited.includes("knowledge") && (
              <div
                className={hubTab === "knowledge" ? "contents" : "hidden"}
                aria-hidden={hubTab !== "knowledge"}
              >
                <KnowledgeView />
              </div>
            )}
            {visited.includes("connectors") && (
              <div
                className={hubTab === "connectors" ? "contents" : "hidden"}
                aria-hidden={hubTab !== "connectors"}
              >
                <ConnectorsHub />
              </div>
            )}
            {visited.includes("browser") && (
              <div
                className={hubTab === "browser" ? "contents" : "hidden"}
                aria-hidden={hubTab !== "browser"}
              >
                <BrowserHub />
              </div>
            )}
            {visited.includes("settings") && (
              <div
                className={hubTab === "settings" ? "contents" : "hidden"}
                aria-hidden={hubTab !== "settings"}
              >
                <div className="w-full pt-8">
                  <Settings />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
