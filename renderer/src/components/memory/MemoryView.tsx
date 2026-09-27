import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useSpacesStore } from "@/store/spaces";
import { useSessionsStore } from "@/store/sessions";
import { migrateLegacyMemorySetting } from "@/lib/memorySettingsMigration";

type MemoryRow = {
  id: number; scope: "global" | "workspace"; workspace: string | null;
  content: string; summary: string | null; created_at: number;
};
type MemorySettings = { enabled: boolean; user_rules: string };

export default function MemoryView() {
  const [rows, setRows] = useState<MemoryRow[]>([]);
  const [settings, setSettings] = useState<MemorySettings>({ enabled: true, user_rules: "" });
  const [rulesDraft, setRulesDraft] = useState("");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [scope, setScope] = useState<"global" | "workspace">("global");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const space = useSpacesStore((state) => state.spaces.find((item) => item.id === state.activeSpaceId));
  const workspace = space?.rootPath || null;
  const projectId = useSessionsStore((state) => state.activeId);
  const hasProjectScope = Boolean(workspace || projectId);

  const request = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const base = await window.api.getBackendUrl();
    if (!base) throw new Error("后端未连接");
    const response = await fetch(`${base}/api/memory${path}`, {
      ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
    if (!response.ok) {
      let detail = `请求失败 (${response.status})`;
      try { detail = ((await response.json()) as { detail?: string }).detail || detail; } catch { /* retain status */ }
      throw new Error(detail);
    }
    return response.json() as Promise<T>;
  }, []);

  const load = useCallback(async () => {
    try {
      const base = await window.api.getBackendUrl();
      if (!base) throw new Error("后端未连接");
      await migrateLegacyMemorySetting(base);
      const [list, next] = await Promise.all([
        request<{ items: MemoryRow[] }>(`/list?limit=500`),
        request<MemorySettings>("/settings"),
      ]);
      setRows(list.items);
      setSettings(next);
      setRulesDraft(next.user_rules);
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
  }, [request]);

  useEffect(() => { void load(); }, [load]);

  async function act(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "操作失败"); }
    finally { setBusy(false); }
  }

  const visible = rows.filter((row) => `${row.content} ${row.summary || ""}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="mx-auto w-full max-w-4xl space-y-5 px-6 py-8">
    <div><h2 className="text-xl font-bold text-ds-text-neutral-default-default">记忆</h2><p className="mt-1 text-sm text-ds-text-neutral-muted-default">长期偏好和项目背景会在新会话开始时提供给代理。</p></div>
    {error ? <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    <section className="rounded-2xl border border-ds-border-neutral-subtle-default bg-white p-5">
      <div className="flex items-center justify-between gap-4"><div><div className="font-semibold">保存新记忆</div><p className="mt-1 text-xs text-ds-text-neutral-muted-default">关闭后，已有记忆仍会用于新会话；代理不再新增、修改或删除记忆。</p></div><Switch aria-label="保存新记忆" checked={settings.enabled} disabled={busy} onCheckedChange={(enabled) => void act(async () => { await request("/settings", { method: "PUT", body: JSON.stringify({ enabled }) }); })} /></div>
      <div className="mt-5 border-t border-ds-border-neutral-subtle-default pt-4"><label className="mb-2 block text-sm font-medium" htmlFor="memory-rules">我的长期规则</label><textarea id="memory-rules" className="min-h-24 w-full rounded-xl border border-ds-border-neutral-strong-default p-3 text-sm" value={rulesDraft} onChange={(event) => setRulesDraft(event.target.value)} placeholder="由你编写的固定规则，优先于代理学习到的记忆" /><div className="mt-2 flex justify-end"><Button size="sm" disabled={busy || rulesDraft === settings.user_rules} onClick={() => void act(async () => { await request("/settings", { method: "PUT", body: JSON.stringify({ user_rules: rulesDraft }) }); })}>保存规则</Button></div></div>
    </section>
    <section className="rounded-2xl border border-ds-border-neutral-subtle-default bg-white p-5">
      <h3 className="font-semibold">手动添加</h3><textarea aria-label="记忆内容" className="mt-3 min-h-20 w-full rounded-xl border border-ds-border-neutral-strong-default p-3 text-sm" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="例如：我希望报告使用简体中文，先给结论。" />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2"><select aria-label="记忆范围" className="rounded-lg border border-ds-border-neutral-strong-default bg-white px-3 py-2 text-sm" value={scope} onChange={(event) => setScope(event.target.value as "global" | "workspace")}><option value="global">所有项目</option><option value="workspace" disabled={!hasProjectScope}>当前项目{hasProjectScope ? ` · ${space?.name || projectId || "当前会话"}` : "（未选择项目）"}</option></select><Button size="sm" disabled={busy || !draft.trim()} onClick={() => void act(async () => { await request("", { method: "POST", body: JSON.stringify({ content: draft.trim(), scope, workspace, project_id: projectId }) }); setDraft(""); })}>添加记忆</Button></div>
    </section>
    <section className="rounded-2xl border border-ds-border-neutral-subtle-default bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">已保存的记忆</h3><p className="text-xs text-ds-text-neutral-muted-default">修改或删除的内容从新会话开始生效。</p></div><input aria-label="搜索记忆" className="rounded-lg border border-ds-border-neutral-strong-default px-3 py-2 text-sm" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索记忆" /></div>
      <div className="mt-4 space-y-2">{visible.map((row) => <div key={row.id} className="rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default p-4"><div className="mb-2 text-xs text-ds-text-neutral-muted-default">{row.scope === "global" ? "所有项目" : `项目 · ${row.workspace || "未知"}`} · #{row.id}</div>{editingId === row.id ? <><textarea aria-label={`编辑记忆 ${row.id}`} className="min-h-20 w-full rounded-lg border border-ds-border-neutral-strong-default bg-white p-2 text-sm" value={editingText} onChange={(event) => setEditingText(event.target.value)} /><div className="mt-2 flex gap-2"><Button size="sm" disabled={busy || !editingText.trim()} onClick={() => void act(async () => { await request(`/${row.id}`, { method: "PATCH", body: JSON.stringify({ content: editingText.trim() }) }); setEditingId(null); })}>保存</Button><Button size="sm" variant="outline" onClick={() => setEditingId(null)}>取消</Button></div></> : <div className="flex items-start justify-between gap-3"><p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm">{row.content}</p><div className="flex shrink-0 gap-1"><Button size="xs" variant="ghost" onClick={() => { setEditingId(row.id); setEditingText(row.content); }}>编辑</Button><Button size="xs" variant="ghost" disabled={busy} onClick={() => void act(async () => { await request(`/${row.id}`, { method: "DELETE" }); })}>删除</Button></div></div>}</div>)}{!visible.length ? <p className="py-8 text-center text-sm text-ds-text-neutral-muted-default">暂无记忆</p> : null}</div>
      {rows.length ? <div className="mt-4 flex justify-end"><Button size="sm" variant="ghost" disabled={busy} onClick={() => { if (!window.confirm("删除所有已保存的记忆？")) return; void act(async () => { await request("", { method: "DELETE" }); }); }}>删除全部</Button></div> : null}
    </section>
  </div>;
}
