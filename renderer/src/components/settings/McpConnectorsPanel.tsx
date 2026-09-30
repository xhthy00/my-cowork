/**
 * Custom MCP connectors — local JSON / remote URL, aligned with eigent dialogs.
 */
import { Eye, EyeOff, Plus, Server, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { SettingsField } from "@/components/settings/SettingsField";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const LOCAL_MCP_EXAMPLE = `{
  "mcpServers": {
    "sequential-thinking": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-sequential-thinking"
      ]
    }
  }
}`;

export interface McpServerEntry {
  command?: string;
  args?: string[] | string;
  description?: string;
  env?: Record<string, string>;
  enabled?: boolean;
  connected?: boolean;
  url?: string;
  headers?: Record<string, string>;
  type?: string;
  transport?: string;
}

function argsList(cfg: McpServerEntry): string[] {
  const raw = cfg.args;
  if (Array.isArray(raw)) return raw.map(String);
  if (typeof raw === "string" && raw.trim()) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      return raw.split(/\s+/).filter(Boolean);
    }
  }
  return [];
}

function isRemote(cfg: McpServerEntry): boolean {
  return Boolean(cfg.url) && !cfg.command;
}

function persistMap(servers: Record<string, McpServerEntry>): Record<string, McpServerEntry> {
  const out: Record<string, McpServerEntry> = {};
  for (const [name, cfg] of Object.entries(servers)) {
    const { connected: _c, ...rest } = cfg;
    out[name] = rest;
  }
  return out;
}

async function readDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail != null) return JSON.stringify(body.detail);
  } catch {
    // ignore
  }
  return `请求失败 ${res.status}`;
}

function KvRows({
  title,
  values,
  secret,
  onChange,
}: {
  title: string;
  values: Record<string, string>;
  secret?: boolean;
  onChange: (next: Record<string, string>) => void;
}) {
  const [show, setShow] = useState<Record<string, boolean>>({});
  const entries = Object.entries(values);
  return (
    <div className="flex flex-col gap-2">
      <div className="text-body-sm font-bold text-ds-text-neutral-default-default">{title}</div>
      {entries.map(([key, value], idx) => (
        <div key={`${key}-${idx}`} className="flex items-end gap-2">
          <SettingsField
            title="键"
            value={key}
            onChange={(e) => {
              const nextKey = e.target.value;
              const next: Record<string, string> = {};
              entries.forEach(([k, v], i) => {
                next[i === idx ? nextKey : k] = v;
              });
              onChange(next);
            }}
            className="flex-1"
          />
          <SettingsField
            title="值"
            type={secret && !show[key] ? "password" : "text"}
            value={value}
            onChange={(e) => onChange({ ...values, [key]: e.target.value })}
            className="flex-1"
            autoComplete="off"
            backIcon={
              secret ? (
                show[key] ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />
              ) : undefined
            }
            onBackIconClick={
              secret
                ? () => setShow((prev) => ({ ...prev, [key]: !prev[key] }))
                : undefined
            }
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              const next = { ...values };
              delete next[key];
              onChange(next);
            }}
          >
            删除
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="self-start"
        onClick={() => {
          let n = 1;
          let key = `KEY_${n}`;
          while (key in values) {
            n += 1;
            key = `KEY_${n}`;
          }
          onChange({ ...values, [key]: "" });
        }}
      >
        添加
      </Button>
    </div>
  );
}

export default function McpConnectorsPanel() {
  const [servers, setServers] = useState<Record<string, McpServerEntry>>({});
  const [status, setStatus] = useState("");
  const [adding, setAdding] = useState(false);
  const [addTab, setAddTab] = useState<"local" | "remote">("local");
  const [localJson, setLocalJson] = useState(LOCAL_MCP_EXAMPLE);
  const [remoteName, setRemoteName] = useState("");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<string | None>(null);
  const [editForm, setEditForm] = useState<McpServerEntry | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 2400);
    return () => window.clearTimeout(id);
  }, [toast]);

  const load = useCallback(async (opts?: { keepStatus?: boolean }) => {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) {
      setStatus("后端未连接");
      return;
    }
    const res = await fetch(`${backendUrl}/api/mcp/servers`);
    if (!res.ok) {
      setStatus(await readDetail(res));
      return;
    }
    const data = (await res.json()) as { mcpServers: Record<string, McpServerEntry> };
    setServers(data.mcpServers || {});
    if (!opts?.keepStatus) setStatus("");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function putAll(next: Record<string, McpServerEntry>) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return;
    const res = await fetch(`${backendUrl}/api/mcp/servers`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mcpServers: persistMap(next) }),
    });
    if (!res.ok) {
      setStatus(await readDetail(res));
      return;
    }
    await load();
  }

  async function importServers(payload: Record<string, McpServerEntry>) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) {
      setStatus("后端未连接");
      return;
    }
    setSaving(true);
    setStatus("正在导入…");
    try {
      let res = await fetch(`${backendUrl}/api/mcp/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mcpServers: payload }),
      });
      if (res.status === 404) {
        const merged = { ...persistMap(servers), ...payload };
        res = await fetch(`${backendUrl}/api/mcp/servers`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mcpServers: merged }),
        });
      }
      if (!res.ok) {
        setStatus(await readDetail(res));
        return;
      }
      setAdding(false);
      await load({ keepStatus: true });
      setStatus("已添加");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function submitAdd() {
    if (addTab === "local") {
      let parsed: { mcpServers?: Record<string, McpServerEntry> };
      try {
        parsed = JSON.parse(localJson);
      } catch (err) {
        setStatus(`JSON 无效：${err instanceof Error ? err.message : String(err)}`);
        return;
      }
      if (!parsed.mcpServers || typeof parsed.mcpServers !== "object") {
        setStatus("缺少 mcpServers");
        return;
      }
      const names = Object.keys(parsed.mcpServers);
      if (!names.length) {
        setStatus("至少添加一个 MCP");
        return;
      }
      await importServers(parsed.mcpServers);
      return;
    }
    const name = remoteName.trim();
    const url = remoteUrl.trim();
    if (!name) {
      setStatus("名称必填");
      return;
    }
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(url);
    } catch {
      setStatus("远程 URL 无效");
      return;
    }
    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      setStatus("远程 URL 须为 http 或 https");
      return;
    }
    await importServers({ [name]: { url } });
  }

  async function saveEdit() {
    if (!editing || !editForm) return;
    await putAll({ ...servers, [editing]: editForm });
    setEditing(null);
    setEditForm(null);
  }

  async function removeServer(key: string) {
    const next = { ...servers };
    delete next[key];
    await putAll(next);
    if (editing === key) {
      setEditing(null);
      setEditForm(null);
    }
  }

  async function toggleEnabled(key: string, checked: boolean) {
    const cur = servers[key];
    if (!cur) return;
    await putAll({ ...servers, [key]: { ...cur, enabled: checked } });
  }

  async function testServer(key: string) {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) {
      setToast({ kind: "err", text: "后端未连接" });
      return;
    }
    setTesting(key);
    try {
      const res = await fetch(
        `${backendUrl}/api/mcp/servers/${encodeURIComponent(key)}/test`,
        { method: "POST" },
      );
      if (!res.ok) {
        setToast({ kind: "err", text: `${key} 连接失败：${await readDetail(res)}` });
        return;
      }
      const body = (await res.json()) as { tools?: string[] };
      const n = (body.tools || []).length;
      setToast({
        kind: "ok",
        text: n ? `${key} 测试通过，${n} 个工具` : `${key} 测试通过`,
      });
      await load({ keepStatus: true });
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setToast({ kind: "err", text: `${key} 连接失败：${detail}` });
    } finally {
      setTesting(null);
    }
  }

  const names = Object.keys(servers);

  return (
    <div className="flex h-auto w-full flex-1 flex-col pb-12">
      <div className="flex w-full flex-wrap items-start justify-between gap-3 pb-6 pt-8">
        <div className="min-w-0">
          <h2 className="text-heading-sm font-bold text-ds-text-neutral-default-default">
            连接器
          </h2>
          <p className="mt-1 text-body-sm text-ds-text-neutral-muted-default">
            本地与远程 MCP
          </p>
        </div>
        <Button
          type="button"
          variant={adding ? "ghost" : "primary"}
          size="sm"
          onClick={() => setAdding((v) => !v)}
        >
          {adding ? (
            "取消"
          ) : (
            <>
              <Plus className="h-4 w-4" />
              添加
            </>
          )}
        </Button>
      </div>

      {toast ? (
        <div
          role="status"
          className={
            toast.kind === "ok"
              ? "pointer-events-none fixed left-1/2 top-16 z-50 -translate-x-1/2 rounded-full bg-ds-bg-status-completed-default-default px-4 py-2 text-body-sm text-white shadow-lg"
              : "pointer-events-none fixed left-1/2 top-16 z-50 -translate-x-1/2 rounded-full bg-[var(--danger,#e7000b)] px-4 py-2 text-body-sm text-white shadow-lg"
          }
        >
          {toast.text}
        </div>
      ) : null}

      {status ? (
        <div
          className={
            /失败|无效|已存在|必填|缺少|Not Found|后端未|须为/.test(status)
              ? "mb-4 rounded-xl px-4 py-3 text-body-sm text-ds-text-error-default-default"
              : "mb-4 rounded-xl bg-ds-bg-neutral-subtle-default px-4 py-3 text-body-sm text-ds-text-neutral-muted-default"
          }
        >
          {status}
        </div>
      ) : null}

      {adding ? (
        <div className="mb-6 flex flex-col gap-5 rounded-2xl bg-ds-bg-neutral-default-default p-6">
          <Tabs value={addTab} onValueChange={(v) => setAddTab(v as "local" | "remote")}>
            <TabsList>
              <TabsTrigger value="local">
                <Wrench className="h-3.5 w-3.5" />
                本地 JSON
              </TabsTrigger>
              <TabsTrigger value="remote">
                <Server className="h-3.5 w-3.5" />
                远程 URL
              </TabsTrigger>
            </TabsList>
            <TabsContent value="local" className="mt-5">
              <label className="flex flex-col gap-2 text-body-sm">
                <span className="text-ds-text-neutral-muted-default">
                  粘贴 Cursor / Claude 格式的 mcp.json
                </span>
                <textarea
                  aria-label="mcp.json"
                  className="min-h-56 w-full rounded-xl border border-solid border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-4 py-3 font-mono text-xs leading-5 text-ds-text-neutral-default-default outline-none focus:border-ds-border-neutral-strong-default"
                  value={localJson}
                  onChange={(e) => setLocalJson(e.target.value)}
                />
              </label>
            </TabsContent>
            <TabsContent value="remote" className="mt-5">
              <div className="flex max-w-xl flex-col gap-4">
                <SettingsField
                  title="名称"
                  placeholder="playwright"
                  value={remoteName}
                  onChange={(e) => setRemoteName(e.target.value)}
                />
                <SettingsField
                  title="远程 URL"
                  placeholder="https://example.com/mcp"
                  value={remoteUrl}
                  onChange={(e) => setRemoteUrl(e.target.value)}
                  note="支持 Streamable HTTP 或 SSE 地址"
                />
              </div>
            </TabsContent>
          </Tabs>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setAdding(false)}
            >
              取消
            </Button>
            <Button type="button" size="sm" disabled={saving} onClick={() => void submitAdd()}>
              {saving ? "导入中…" : "导入"}
            </Button>
          </div>
        </div>
      ) : null}

      {names.length === 0 && !adding ? (
        <div
          className="flex w-full flex-col items-center justify-center gap-3 rounded-2xl bg-ds-bg-neutral-subtle-default px-6 py-10 text-body-sm text-ds-text-neutral-muted-default"
        >
          还没有连接器，点击右上角添加本地或远程 MCP。
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {Object.entries(servers).map(([key, cfg]) => (
            <div
              key={key}
              className="flex flex-col gap-4 rounded-2xl bg-ds-bg-neutral-default-default px-5 py-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-body-sm font-bold text-ds-text-neutral-default-default">
                      {key}
                    </span>
                    {cfg.connected ? (
                      <span className="shrink-0 text-label-sm text-ds-text-success-default-default">
                        已连接
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 truncate font-mono text-label-sm text-ds-text-neutral-muted-default">
                    {isRemote(cfg)
                      ? cfg.url
                      : `${cfg.command || ""} ${argsList(cfg).join(" ")}`.trim()}
                  </div>
                  {cfg.description ? (
                    <p className="mt-1 text-body-sm text-ds-text-neutral-muted-default">
                      {cfg.description}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Switch
                    checked={cfg.enabled ?? true}
                    onCheckedChange={(checked) => void toggleEnabled(key, checked)}
                    aria-label={`启用 ${key}`}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={testing === key}
                    onClick={() => void testServer(key)}
                  >
                    {testing === key ? "测试中…" : "测试"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setEditing(key);
                      setEditForm({
                        ...cfg,
                        args: argsList(cfg),
                        env: { ...(cfg.env || {}) },
                        headers: { ...(cfg.headers || {}) },
                      });
                    }}
                  >
                    编辑
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => void removeServer(key)}
                  >
                    删除
                  </Button>
                </div>
              </div>
              {editing === key && editForm ? (
                <div className="flex max-w-xl flex-col gap-4 border-t border-solid border-ds-border-neutral-subtle-default pt-4">
                  <SettingsField
                    title="描述"
                    value={editForm.description || ""}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  />
                  {isRemote(editForm) ? (
                    <>
                      <SettingsField
                        title="远程 URL"
                        value={editForm.url || ""}
                        onChange={(e) => setEditForm({ ...editForm, url: e.target.value })}
                      />
                      <KvRows
                        title="Headers（可选）"
                        values={editForm.headers || {}}
                        onChange={(headers) => setEditForm({ ...editForm, headers })}
                      />
                    </>
                  ) : (
                    <>
                      <SettingsField
                        title="命令"
                        value={editForm.command || ""}
                        onChange={(e) => setEditForm({ ...editForm, command: e.target.value })}
                      />
                      <label className="flex flex-col gap-1.5 text-body-sm">
                        <span className="font-bold text-ds-text-neutral-default-default">
                          参数（每行一个）
                        </span>
                        <textarea
                          aria-label="参数（每行一个）"
                          className="min-h-24 rounded-xl border border-solid border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 py-2 font-mono text-xs outline-none"
                          value={argsList(editForm).join("\n")}
                          onChange={(e) =>
                            setEditForm({
                              ...editForm,
                              args: e.target.value.split(/\r?\n/),
                            })
                          }
                        />
                      </label>
                      <KvRows
                        title="环境变量"
                        secret
                        values={editForm.env || {}}
                        onChange={(env) => setEditForm({ ...editForm, env })}
                      />
                    </>
                  )}
                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditing(null);
                        setEditForm(null);
                      }}
                    >
                      取消
                    </Button>
                    <Button type="button" size="sm" onClick={() => void saveEdit()}>
                      保存
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
