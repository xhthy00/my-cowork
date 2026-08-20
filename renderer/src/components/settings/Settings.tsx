import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { Appearance } from "../../lib/appearance";
import { useSettingsStore } from "../../store/settings";
import ModelsPanel from "./ModelsPanel";
import McpConnectorsPanel from "./McpConnectorsPanel";
import ChannelsPanel from "./channels/ChannelsPanel";
import SearchPanel from "./SearchPanel";

type TabId = "general" | "model" | "appearance" | "paths" | "channels" | "mcp" | "search";

const TABS: { id: TabId; label: string }[] = [
  { id: "general", label: "通用" },
  { id: "model", label: "API / 模型" },
  { id: "appearance", label: "外观" },
  { id: "paths", label: "隐私 / 白名单" },
  { id: "mcp", label: "连接器 / MCP" },
  { id: "search", label: "检索" },
  { id: "channels", label: "远程连接" },
];

const APPEARANCE_OPTIONS: { id: Appearance; label: string }[] = [
  { id: "light", label: "浅色" },
  { id: "dark", label: "深色" },
  { id: "system", label: "跟随系统" },
];

export default function Settings({ embedded = false }: { embedded?: boolean }) {
  const [tab, setTab] = useState<TabId>("model");
  const whitelist = useSettingsStore((s) => s.whitelist);
  const setWhitelist = useSettingsStore((s) => s.setWhitelist);
  const appearance = useSettingsStore((s) => s.appearance);
  const setAppearance = useSettingsStore((s) => s.setAppearance);

  const [draftPaths, setDraftPaths] = useState<string[]>(whitelist);
  const [newPath, setNewPath] = useState("");
  const [status, setStatus] = useState("");

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

  return (
    <div
      className={embedded ? "settings-embedded" : "view active"}
      id="view-settings"
    >
      {!embedded && (
        <div className="view-header">
          <h1>设置</h1>
        </div>
      )}
      <div className={embedded ? undefined : "view-content"}>
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
              <div>
                <h3>通用</h3>
                <p className="panel-desc">应用更新与基础信息。</p>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={async () => {
                    if (!window.api?.checkForUpdates) return;
                    const r = await window.api.checkForUpdates();
                    setStatus(r.message);
                  }}
                >
                  检查更新
                </button>
                {status && tab === "general" && (
                  <p className="form-hint" style={{ marginTop: 8 }}>
                    {status}
                  </p>
                )}
              </div>
            )}

            {!embedded && tab === "appearance" && (
              <div>
                <h3>外观</h3>
                <p className="panel-desc">界面主题。跟随系统会随操作系统自动切换。</p>
                <div className="preset-row">
                  {APPEARANCE_OPTIONS.map((opt) => (
                    <Button
                      key={opt.id}
                      type="button"
                      variant={appearance === opt.id ? "primary" : "outline"}
                      size="sm"
                      onClick={() => setAppearance(opt.id)}
                    >
                      {opt.label}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {(embedded || tab === "model") && <ModelsPanel />}

            {!embedded && tab === "paths" && (
              <div>
                <h3>目录白名单</h3>
                <p className="panel-desc">
                  fs / exec 工具的 path 必须 resolve 后落在白名单内，越界直接 ToolError。
                </p>
                <div className="path-list">
                  {draftPaths.map((path) => (
                    <div className="path-item" key={path}>
                      <code>{path}</code>
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
                <div className="form-group" style={{ marginTop: 12 }}>
                  <input
                    type="text"
                    placeholder="例如 ~/Projects"
                    value={newPath}
                    onChange={(e) => setNewPath(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") addPath();
                    }}
                  />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-ghost" type="button" onClick={addPath}>
                    + 添加目录…
                  </button>
                  <button className="btn btn-primary" type="button" onClick={saveWhitelist}>
                    保存白名单
                  </button>
                </div>
              </div>
            )}

            {!embedded && tab === "mcp" && <McpConnectorsPanel />}
            {!embedded && tab === "search" && <SearchPanel />}
            {!embedded && tab === "channels" && <ChannelsPanel />}
          </div>
        </div>
      </div>
    </div>
  );
}
