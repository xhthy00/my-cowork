/**
 * Adapted from eigent Connectors Custom MCP dialogs (local MCP only).
 */
import { useCallback, useEffect, useState } from "react";

interface McpServerEntry {
  command?: string;
  args?: string[];
  description?: string;
  env?: Record<string, string>;
  enabled?: boolean;
  connected?: boolean;
}

export default function McpConnectorsPanel() {
  const [servers, setServers] = useState<Record<string, McpServerEntry>>({});
  const [status, setStatus] = useState("");
  const [name, setName] = useState("");
  const [command, setCommand] = useState("npx");
  const [args, setArgs] = useState("-y @playwright/mcp@latest");
  const [description, setDescription] = useState("");

  const load = useCallback(async () => {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) {
      setStatus("后端未连接");
      return;
    }
    const res = await fetch(`${backendUrl}/api/mcp/servers`);
    if (!res.ok) {
      setStatus(`加载失败 ${res.status}`);
      return;
    }
    const data = (await res.json()) as { mcpServers: Record<string, McpServerEntry> };
    setServers(data.mcpServers || {});
    setStatus("");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(next: Record<string, McpServerEntry>) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    await fetch(`${backendUrl}/api/mcp/servers`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mcpServers: next }),
    });
    setServers(next);
  }

  async function reload() {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    setStatus("正在重新加载…");
    const res = await fetch(`${backendUrl}/api/mcp/reload`, { method: "POST" });
    setStatus(res.ok ? "已重新加载" : `重新加载失败 ${res.status}`);
    await load();
  }

  async function addServer() {
    const key = name.trim();
    if (!key || !command.trim()) return;
    const next = {
      ...servers,
      [key]: {
        command: command.trim(),
        args: args.split(/\s+/).filter(Boolean),
        description: description.trim(),
        enabled: true,
      },
    };
    await save(next);
    setName("");
    setDescription("");
  }

  async function removeServer(key: string) {
    const next = { ...servers };
    delete next[key];
    await save(next);
  }

  async function toggleEnabled(key: string) {
    const cur = servers[key];
    if (!cur) return;
    await save({
      ...servers,
      [key]: { ...cur, enabled: !(cur.enabled ?? true) },
    });
  }

  return (
    <div>
      <div className="settings-section-head" style={{ display: "flex", justifyContent: "space-between" }}>
        <h3>本地 MCP</h3>
        <button type="button" className="btn btn-ghost" onClick={() => void reload()}>
          重新加载
        </button>
      </div>
      {status && <p className="form-hint">{status}</p>}
      <div className="mcp-list">
        {Object.entries(servers).map(([key, cfg]) => (
          <div key={key} className="mcp-row">
            <div>
              <div className="name">
                {key} {cfg.connected ? "· 已连接" : ""}
              </div>
              <div className="cmd">
                {cfg.command} {(cfg.args || []).join(" ")}
              </div>
              {cfg.description && <p className="form-hint">{cfg.description}</p>}
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                className={`toggle ${(cfg.enabled ?? true) ? "on" : ""}`}
                role="switch"
                aria-checked={cfg.enabled ?? true}
                onClick={() => void toggleEnabled(key)}
              />
              <button type="button" className="btn btn-ghost" onClick={() => void removeServer(key)}>
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="mcp-form">
        <h4>添加自定义 MCP</h4>
        <input placeholder="名称（如 playwright）" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="命令" value={command} onChange={(e) => setCommand(e.target.value)} />
        <input placeholder="args（空格分隔）" value={args} onChange={(e) => setArgs(e.target.value)} />
        <input
          placeholder="描述"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button type="button" className="btn" onClick={() => void addServer()}>
          添加
        </button>
      </div>
    </div>
  );
}
