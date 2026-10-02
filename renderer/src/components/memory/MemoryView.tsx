import { apiFetch as fetch } from "@/api/backend";
import { Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { MEMORY_CHANGED_EVENT } from "@/lib/memoryEvents";
import { migrateLegacyMemorySetting } from "@/lib/memorySettingsMigration";

type MemoryRow = {
  id: number;
  scope: "global" | "workspace";
  workspace: string | null;
  content: string;
  summary: string | null;
  created_at: number;
};
type MemorySettings = { enabled: boolean; user_rules: string };

const cardClass = "rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-4 sm:p-5";
const fieldClass = "w-full rounded-lg border border-ds-border-neutral-strong-default bg-ds-bg-neutral-subtle-default px-3 py-2.5 text-sm leading-relaxed text-ds-text-neutral-default-default outline-none placeholder:text-ds-text-neutral-subtle-default focus:border-ds-border-information-default-default focus:ring-2 focus:ring-ds-ring-neutral-subtle-default";

export default function MemoryView() {
  const [rows, setRows] = useState<MemoryRow[]>([]);
  const [settings, setSettings] = useState<MemorySettings | null>(null);
  const [rulesDraft, setRulesDraft] = useState("");
  const savedRules = useRef("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toggleMessage, setToggleMessage] = useState("");
  const [listMessage, setListMessage] = useState("");
  const [rulesMessage, setRulesMessage] = useState("");

  const request = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const base = await window.api.getBackendUrl();
    if (!base) throw new Error("后端未连接");
    const response = await fetch(`${base}/api/memory${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
    if (!response.ok) {
      let detail = `请求失败 (${response.status})`;
      try {
        detail = ((await response.json()) as { detail?: string }).detail || detail;
      } catch { /* Retain the HTTP status. */ }
      throw new Error(detail);
    }
    return response.json() as Promise<T>;
  }, []);

  const refresh = useCallback(async () => {
    const base = await window.api.getBackendUrl();
    if (!base) throw new Error("后端未连接");
    await migrateLegacyMemorySetting(base);
    const [list, next] = await Promise.all([
      request<{ items: MemoryRow[] }>("/list?limit=500"),
      request<MemorySettings>("/settings"),
    ]);
    setRows(list.items);
    setSettings(next);
    setRulesDraft((current) => current === savedRules.current ? next.user_rules : current);
    savedRules.current = next.user_rules;
    setError("");
  }, [request]);

  useEffect(() => {
    let mounted = true;
    const reload = () => {
      void refresh().catch((cause) => {
        if (mounted) setError(cause instanceof Error ? cause.message : "加载失败");
      });
    };
    reload();
    window.addEventListener(MEMORY_CHANGED_EVENT, reload);
    window.addEventListener("focus", reload);
    return () => {
      mounted = false;
      window.removeEventListener(MEMORY_CHANGED_EVENT, reload);
      window.removeEventListener("focus", reload);
    };
  }, [refresh]);

  async function act(work: () => Promise<unknown>, onSuccess?: () => void) {
    setBusy(true);
    setError("");
    try {
      await work();
      await refresh();
      onSuccess?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  function saveRow(id: number) {
    const content = editingText.trim();
    if (!content || busy) return;
    const original = rows.find((row) => row.id === id)?.content;
    if (content === original) {
      setEditingId(null);
      return;
    }
    void act(
      () => request(`/${id}`, { method: "PATCH", body: JSON.stringify({ content }) }),
      () => { setEditingId(null); setListMessage("记忆已更新，将在新会话中生效。"); },
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 px-6 pb-8 pt-2">
      <header className="mb-1">
        <p className="text-sm text-ds-text-neutral-muted-default">智能体可以跨会话记住关于你的有用信息。已记住的内容都列在这里。</p>
      </header>

      {error && <div role="alert" className="rounded-lg border border-[var(--danger)] bg-[var(--danger-soft)] px-3 py-2.5 text-sm text-ds-text-error-default-default">{error}</div>}
      {!settings ? (
        <div className={cardClass} role="status">
          {error
            ? <Button variant="outline" onClick={() => void refresh().catch((cause) => setError(cause instanceof Error ? cause.message : "加载失败"))}>重试</Button>
            : <span className="text-sm text-ds-text-neutral-muted-default">正在加载记忆…</span>}
        </div>
      ) : (
        <>
          <section className={cardClass} data-testid="memory-toggle-card">
            <div className="flex items-start gap-3">
              <Switch
                className="mt-0.5"
                aria-labelledby="memory-toggle-label"
                checked={settings.enabled}
                disabled={busy}
                onCheckedChange={(enabled) => void act(
                  () => request("/settings", { method: "PUT", body: JSON.stringify({ enabled }) }),
                  () => setToggleMessage(enabled
                    ? "以后会话中分享的长期偏好会被记住。"
                    : "已停止保存新记忆。已有内容仍会使用，直到你在下方删除。"),
                )}
              />
              <div className="min-w-0 flex-1">
                <h3 id="memory-toggle-label" className="text-sm font-semibold text-ds-text-neutral-default-default">记住关于我的新信息</h3>
                <p className="mt-1 text-xs leading-relaxed text-ds-text-neutral-muted-default">聊天中提到的长期偏好可用于以后会话。每次保存都会提示，并可撤销。关闭后不再保存新内容；已有记忆仍会使用。</p>
              </div>
            </div>
            {toggleMessage && <p role="status" className="mt-3 border-t border-ds-border-neutral-subtle-default pt-3 text-xs leading-relaxed text-ds-text-neutral-muted-default">{toggleMessage}</p>}
          </section>

          <section className={cardClass} data-testid="memory-list-card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-ds-text-neutral-default-default">我对你的了解</h3>
                <p className="mt-1 text-xs leading-relaxed text-ds-text-neutral-muted-default">自动从会话中保存。有错可以修正，也可以删除；更改从新会话开始生效。</p>
              </div>
              {rows.length > 0 && <button
                type="button"
                className="shrink-0 rounded-md px-2 py-1 text-xs text-ds-text-error-default-default hover:bg-[var(--danger-soft)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-text-error-default-default disabled:opacity-50"
                disabled={busy}
                onClick={() => {
                  if (!window.confirm("删除所有已记住的内容？此操作无法撤销，已打开的会话仍保留开始时的记忆。")) return;
                  void act(() => request("", { method: "DELETE" }), () => setListMessage("已删除所有记忆。新会话将从空白记忆开始。"));
                }}
              >忘掉全部…</button>}
            </div>
            {listMessage && <p role="status" className="mt-3 text-xs text-ds-text-neutral-muted-default">{listMessage}</p>}
            {rows.length === 0 ? (
              !listMessage && <p className="mt-4 text-sm leading-relaxed text-ds-text-neutral-muted-default">暂时没有记忆。在聊天中提到长期偏好，或说“记住……”，内容就会显示在这里。</p>
            ) : (
              <div className="mt-3 divide-y divide-ds-border-neutral-subtle-default">
                {rows.map((row) => <div key={row.id} className="py-3 first:pt-2 last:pb-0" data-testid={`memory-row-${row.id}`}>
                  {editingId === row.id ? (
                    <div>
                      <textarea
                        aria-label={`编辑记忆 ${row.id}`}
                        autoFocus
                        rows={2}
                        className={fieldClass}
                        value={editingText}
                        onChange={(event) => setEditingText(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); saveRow(row.id); }
                          if (event.key === "Escape") setEditingId(null);
                        }}
                      />
                      <div className="mt-2 flex items-center gap-2">
                        <Button size="sm" disabled={busy || !editingText.trim()} onClick={() => saveRow(row.id)}>保存</Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>取消</Button>
                      </div>
                    </div>
                  ) : (
                    <div className="group flex items-start gap-2">
                      <p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-relaxed text-ds-text-neutral-default-default">{row.content}</p>
                      <button type="button" aria-label={`修正记忆：${row.content}`} title="修正" className="rounded-md p-1.5 text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-default-hover hover:text-ds-text-neutral-default-default focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-border-information-default-default" onClick={() => { setEditingId(row.id); setEditingText(row.content); }}><Pencil size={15} aria-hidden="true" /></button>
                      <button type="button" aria-label={`删除记忆：${row.content}`} title="删除这条记忆" disabled={busy} className="rounded-md p-1.5 text-ds-icon-neutral-muted-default hover:bg-[var(--danger-soft)] hover:text-ds-text-error-default-default focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-text-error-default-default disabled:opacity-50" onClick={() => void act(() => request(`/${row.id}`, { method: "DELETE" }), () => setListMessage("这条记忆已删除，将在新会话中生效。"))}><Trash2 size={15} aria-hidden="true" /></button>
                    </div>
                  )}
                </div>)}
              </div>
            )}
          </section>

          <section className={cardClass} data-testid="user-rules-card">
            <h3 className="text-sm font-semibold text-ds-text-neutral-default-default">你的指令</h3>
            <p className="mt-1 text-xs leading-relaxed text-ds-text-neutral-muted-default">智能体会在每个新会话中遵循这些由你编写的指令。此设置不受上方记忆开关影响。</p>
            <textarea
              aria-label="你的指令"
              rows={4}
              maxLength={20000}
              className={`${fieldClass} mt-3 resize-y`}
              value={rulesDraft}
              onChange={(event) => { setRulesDraft(event.target.value); setRulesMessage(""); }}
              placeholder="例如：报告先写结论；日期使用 YYYY-MM-DD。"
            />
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <Button size="sm" disabled={busy || rulesDraft === settings.user_rules} onClick={() => void act(
                () => request("/settings", { method: "PUT", body: JSON.stringify({ user_rules: rulesDraft }) }),
                () => setRulesMessage("已保存，将从新会话开始生效。"),
              )}>保存</Button>
              {rulesMessage && <span role="status" className="text-xs text-ds-text-neutral-muted-default">{rulesMessage}</span>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
