import { useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { Appearance } from "../../lib/appearance";
import { useSettingsStore } from "../../store/settings";
import ModelsPanel from "./ModelsPanel";
import ChannelsPanel from "./channels/ChannelsPanel";
import SearchPanel from "./SearchPanel";
import ScheduleView from "@/components/schedule/ScheduleView";
import { openKeepAwakeSettings, takeSettingsTabPending } from "./KeepAwakeBanner";

type TabId = "general" | "schedule" | "model" | "paths" | "channels" | "search";

const TABS: { id: TabId; label: string }[] = [
  { id: "general", label: "通用" },
  { id: "schedule", label: "定时任务" },
  { id: "model", label: "API / 模型" },
  { id: "paths", label: "隐私 / 白名单" },
  { id: "search", label: "检索" },
  { id: "channels", label: "远程连接" },
];

const APPEARANCE_OPTIONS: { id: Appearance; label: string }[] = [
  { id: "light", label: "浅色" },
  { id: "dark", label: "深色" },
  { id: "system", label: "跟随系统" },
];

function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex w-full flex-col items-start justify-between">
      <div className="text-body-base mb-4 w-full border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default px-3 py-2 font-bold text-ds-text-neutral-default-default">
        {title}
      </div>
      <div className="flex w-full flex-col gap-4 px-3">{children}</div>
    </div>
  );
}

function SettingsCard({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("w-full rounded-2xl bg-ds-bg-neutral-subtle-default", className)}>
      {children}
    </div>
  );
}

export default function Settings({ embedded = false }: { embedded?: boolean }) {
  const [tab, setTab] = useState<TabId>(() => {
    const pending = takeSettingsTabPending();
    return pending === "general" || pending === "schedule" ? pending : "model";
  });
  const whitelist = useSettingsStore((s) => s.whitelist);
  const setWhitelist = useSettingsStore((s) => s.setWhitelist);
  const appearance = useSettingsStore((s) => s.appearance);
  const setAppearance = useSettingsStore((s) => s.setAppearance);

  const [draftPaths, setDraftPaths] = useState<string[]>(whitelist);
  const [newPath, setNewPath] = useState("");
  const [status, setStatus] = useState("");
  const [keepAwake, setKeepAwake] = useState(false);
  const [keepAwakeSupported, setKeepAwakeSupported] = useState(true);
  const [keepAwakeError, setKeepAwakeError] = useState("");
  const [keepAwakeBusy, setKeepAwakeBusy] = useState(false);

  useEffect(() => {
    void (async () => {
      const state = await window.api.getKeepAwake?.();
      if (!state) return;
      setKeepAwake(state.enabled);
      setKeepAwakeSupported(state.supported);
    })();
  }, []);

  useEffect(() => {
    const onNav = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail === "settings-general") {
        takeSettingsTabPending();
        setTab("general");
      } else if (detail === "settings-schedule") {
        takeSettingsTabPending();
        setTab("schedule");
      } else if (detail === "models") {
        setTab("model");
      }
    };
    window.addEventListener("my-cowork:navigate", onNav);
    return () => window.removeEventListener("my-cowork:navigate", onNav);
  }, []);

  async function saveWhitelist() {
    const backendUrl = await window.api.getBackendUrl();
    if (backendUrl) {
      await fetch(`${backendUrl}/api/admin/whitelist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: draftPaths }),
      });
    }
    setWhitelist(draftPaths);
  }

  function addPath() {
    const path = newPath.trim();
    if (!path || draftPaths.includes(path)) return;
    setDraftPaths([...draftPaths, path]);
    setNewPath("");
  }

  function removePath(path: string) {
    setDraftPaths(draftPaths.filter((p) => p !== path));
  }

  async function onKeepAwakeChange(checked: boolean) {
    const previous = keepAwake;
    setKeepAwake(checked);
    setKeepAwakeError("");
    setKeepAwakeBusy(true);
    try {
      const result = await window.api.setKeepAwake?.({ enabled: checked });
      if (!result?.ok) {
        setKeepAwake(previous);
        setKeepAwakeError(result?.error || "无法更新保持唤醒");
        return;
      }
      setKeepAwake(result.enabled);
    } catch (err) {
      setKeepAwake(previous);
      setKeepAwakeError(err instanceof Error ? err.message : String(err));
    } finally {
      setKeepAwakeBusy(false);
    }
  }

  return (
    <div
      className={embedded ? "settings-embedded" : "w-full"}
      id="view-settings"
    >
      <div className={embedded ? undefined : "w-full"}>
        <div className="settings-layout">
          {!embedded && (
            <nav className="settings-nav">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={tab === t.id ? "active" : ""}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </nav>
          )}

          <div className="settings-panel">
            {!embedded && tab === "general" && (
              <SettingsSection title="通用">
                <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2">
                  <SettingsCard>
                    <div className="flex h-full items-start justify-between gap-4 px-5 py-4">
                      <div className="min-w-0">
                        <label
                          htmlFor="keep-awake-switch"
                          className="text-body-base font-bold text-ds-text-neutral-default-default"
                        >
                          保持唤醒
                        </label>
                        <p className="mt-1 text-body-sm text-ds-text-neutral-muted-default">
                          阻止因空闲休眠，远程通道与定时任务可在熄屏后继续。合盖或手动睡眠仍会中断。
                        </p>
                        {keepAwakeError ? (
                          <p className="mt-2 text-body-sm text-ds-text-error-default-default" role="alert">
                            {keepAwakeError}
                          </p>
                        ) : null}
                      </div>
                      <Switch
                        id="keep-awake-switch"
                        className="mt-0.5"
                        checked={keepAwake}
                        disabled={!keepAwakeSupported || keepAwakeBusy}
                        onCheckedChange={(checked) => void onKeepAwakeChange(checked)}
                        aria-label="保持唤醒"
                      />
                    </div>
                  </SettingsCard>
                  <SettingsCard>
                    <div className="flex h-full items-start justify-between gap-4 px-5 py-4">
                      <div className="min-w-0">
                        <div className="text-body-base font-bold text-ds-text-neutral-default-default">
                          应用更新
                        </div>
                        <p className="mt-1 text-body-sm text-ds-text-neutral-muted-default">
                          检查并安装最新版本。
                        </p>
                        {status ? (
                          <p className="mt-2 text-body-sm text-ds-text-neutral-muted-default">{status}</p>
                        ) : null}
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        className="mt-0.5 shrink-0"
                        onClick={async () => {
                          if (!window.api?.checkForUpdates) return;
                          const r = await window.api.checkForUpdates();
                          setStatus(r.message);
                        }}
                      >
                        检查更新
                      </Button>
                    </div>
                  </SettingsCard>
                  <SettingsCard className="sm:col-span-2">
                    <div className="px-5 py-4">
                      <div className="text-body-base font-bold text-ds-text-neutral-default-default">
                        界面主题
                      </div>
                      <p className="mt-1 text-body-sm text-ds-text-neutral-muted-default">
                        跟随系统会随操作系统自动切换。
                      </p>
                      <div className="mt-3 grid grid-cols-3 gap-2">
                        {APPEARANCE_OPTIONS.map((opt) => (
                          <Button
                            key={opt.id}
                            type="button"
                            variant={appearance === opt.id ? "primary" : "outline"}
                            size="sm"
                            className="w-full"
                            onClick={() => setAppearance(opt.id)}
                          >
                            {opt.label}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </SettingsCard>
                </div>
              </SettingsSection>
            )}

            {!embedded && tab === "schedule" && <ScheduleView />}

            {(embedded || tab === "model") && <ModelsPanel />}

            {!embedded && tab === "paths" && (
              <SettingsSection title="目录白名单">
                <SettingsCard>
                  <div className="px-6 py-5">
                    <p className="text-body-sm text-ds-text-neutral-muted-default">
                      fs / exec 工具的 path 必须 resolve 后落在白名单内，越界直接 ToolError。
                    </p>
                    <div className="mt-4 overflow-hidden rounded-xl bg-ds-bg-neutral-default-default">
                      {draftPaths.map((path) => (
                        <div
                          className="flex items-center justify-between gap-3 border-b border-ds-border-neutral-subtle-default px-4 py-2.5 last:border-b-0"
                          key={path}
                        >
                          <code className="min-w-0 truncate text-body-sm text-ds-text-neutral-default-default">
                            {path}
                          </code>
                          <button
                            className="icon-btn"
                            type="button"
                            title="移除"
                            onClick={() => removePath(path)}
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M18 6L6 18M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4">
                      <input
                        className="h-10 w-full rounded-xl border-0 bg-ds-bg-neutral-default-default px-3 text-body-sm text-ds-text-neutral-default-default outline-none placeholder:text-ds-text-neutral-subtle-default"
                        type="text"
                        placeholder="例如 ~/Projects"
                        value={newPath}
                        onChange={(e) => setNewPath(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") addPath();
                        }}
                      />
                    </div>
                    <div className="mt-4 flex gap-2">
                      <Button type="button" variant="outline" size="sm" onClick={addPath}>
                        + 添加目录…
                      </Button>
                      <Button type="button" onClick={saveWhitelist}>
                        保存白名单
                      </Button>
                    </div>
                  </div>
                </SettingsCard>
              </SettingsSection>
            )}

            {!embedded && tab === "search" && <SearchPanel />}
            {!embedded && tab === "channels" && (
              <ChannelsPanel onOpenKeepAwake={openKeepAwakeSettings} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
