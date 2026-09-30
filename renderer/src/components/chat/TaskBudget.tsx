import { apiFetch as fetch } from "@/api/backend";
import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/button";
import { useBackendEpoch } from "@/hooks/useBackendEpoch";
import { useSessionStore } from "@/store/session";
import { ensureActiveSession, useSessionsStore } from "@/store/sessions";
import { getProjectTaskId } from "@/store/livePark";

export type TaskBudget = { max_tokens: number | null };

async function budgetRequest<T = TaskBudget>(path: string, method = "GET", body?: TaskBudget): Promise<T> {
  const url = await window.api.getBackendUrl();
  if (!url) throw new Error("本地服务未连接");
  const response = await fetch(`${url}${path}`, {
    method, headers: { "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "预算设置失败");
  return data;
}

export function BudgetEditor({ value, inherit = false, minimum = 1, submitLabel = "保存", onSave }: {
  value?: TaskBudget; inherit?: boolean; minimum?: number; submitLabel?: string;
  onSave: (value: TaskBudget | undefined) => Promise<void> | void;
}) {
  const [mode, setMode] = useState(value === undefined && inherit ? "inherit" : value?.max_tokens === null ? "unlimited" : "custom");
  const [amount, setAmount] = useState(String(value?.max_tokens ?? 200_000));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <form className="flex flex-wrap items-center gap-2" onSubmit={async (event) => {
    event.preventDefault();
    const n = Number(amount);
    if (mode === "custom" && (!Number.isSafeInteger(n) || n < minimum)) {
      setError(`总额度至少为 ${minimum.toLocaleString()} token，请输入整数`); return;
    }
    setBusy(true); setError("");
    try { await onSave(mode === "inherit" ? undefined : { max_tokens: mode === "unlimited" ? null : n }); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }}>
    <select aria-label="预算方式" value={mode} disabled={busy} onChange={(e) => setMode(e.target.value)}
      className="h-9 rounded-lg border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default px-2 text-body-sm">
      {inherit && <option value="inherit">跟随全局</option>}
      <option value="custom">自定义额度</option><option value="unlimited">无上限</option>
    </select>
    {mode === "custom" && <label className="flex items-center gap-2 text-body-sm">
      <input aria-label="任务总额度" type="number" min={minimum} step={1} value={amount} disabled={busy}
        onChange={(e) => setAmount(e.target.value)} className="h-9 w-32 rounded-lg border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default px-3" />
      <span className="text-ds-text-neutral-muted-default">token</span>
    </label>}
    <Button type="submit" size="sm" disabled={busy}>{busy ? "保存中…" : submitLabel}</Button>
    {error && <p role="alert" className="w-full text-body-xs text-[var(--danger)]">{error}</p>}
  </form>;
}

export function GlobalTaskBudget() {
  const epoch = useBackendEpoch();
  const [value, setValue] = useState<TaskBudget>();
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [paused, setPaused] = useState<Array<{ task_id: string; text: string; tokens: number; max_tokens: number | null; required_tokens: number }>>([]);
  useEffect(() => {
    let alive = true;
    setValue(undefined); setError("");
    budgetRequest("/api/budget/settings").then((v) => { if (alive) setValue(v); }).catch((e) => { if (alive) setError(e.message); });
    const refresh = () => budgetRequest<{ tasks: typeof paused }>("/api/budget/paused").then((v) => { if (alive) setPaused(v.tasks ?? []); }).catch(() => {});
    void refresh();
    const timer = setInterval(refresh, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [epoch]);
  return <div className="space-y-3 px-5 py-4">
    <div><p className="text-body-base font-bold">任务预算</p>
      <p className="mt-1 text-body-xs text-ds-text-neutral-muted-default">每个新任务的累计 token 额度，会话可单独设置。</p></div>
    {value && <BudgetEditor key={String(value.max_tokens)} value={value} onSave={async (v) => {
      if (!v) return;
      setValue(await budgetRequest("/api/budget/settings", "PUT", v)); setSaved(true);
    }} />}
    {error && <p role="alert" className="text-body-xs text-[var(--danger)]">{error}</p>}
    {saved && <p role="status" className="text-body-xs text-ds-text-neutral-muted-default">已保存，下个任务生效</p>}
    {paused.map((task) => <div key={task.task_id} className="border-t border-ds-border-neutral-default-default pt-3">
      <p className="mb-2 truncate text-body-sm" title={task.text}>{task.text || task.task_id}</p>
      <BudgetResumePanel taskId={task.task_id} used={task.tokens} cap={task.max_tokens} required={task.required_tokens} onResolved={() => setPaused((rows) => rows.filter((row) => row.task_id !== task.task_id))} />
    </div>)}
  </div>;
}

export function SessionTaskBudget({ running }: { running: boolean }) {
  const project = useSessionsStore((s) => s.sessions.find((p) => p.id === s.activeId));
  const [open, setOpen] = useState(false);
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger asChild><button type="button" disabled={running} className="rounded-lg px-2 py-1 text-label-xs text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default disabled:opacity-50">任务预算</button></Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30" />
      <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(440px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-2xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default p-5 text-ds-text-neutral-default-default shadow-xl">
        <Dialog.Title className="text-body-base font-semibold">会话任务预算</Dialog.Title>
        <Dialog.Description className="text-body-sm text-ds-text-neutral-muted-default">每个新任务单独计数，下个任务生效。</Dialog.Description>
        <BudgetEditor value={project?.taskBudget} inherit onSave={(value) => {
          const id = project?.id ?? ensureActiveSession();
          useSessionsStore.getState().touchSession(id, { taskBudget: value }); setOpen(false);
        }} />
        <Dialog.Close asChild><Button variant="ghost" size="sm">取消</Button></Dialog.Close>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

export function PausedTaskBudget() {
  const paused = useSessionStore((s) => s.budgetPaused);
  const used = useSessionStore((s) => s.budgetTokens);
  const required = useSessionStore((s) => s.budgetRequiredTokens);
  const cap = useSessionStore((s) => s.budgetMaxTokens);
  const activeId = useSessionsStore((s) => s.activeId);
  if (!paused || !activeId) return null;
  const taskId = getProjectTaskId(activeId);
  if (!taskId) return null;
  return <BudgetResumePanel taskId={taskId} used={used} cap={cap} required={required} />;
}

export function BudgetResumePanel({ taskId, used, cap, required, onResolved }: {
  taskId: string; used: number; cap: number | null; required: number; onResolved?: () => void | Promise<void>;
}) {
  const minimum = used + required;
  return <div role="status" className="mx-3 mb-2 space-y-2 rounded-xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default p-3">
    <p className="text-body-sm font-medium">预算不足，任务已暂停 · 已用 {used.toLocaleString()} token</p>
    <BudgetEditor key={`${taskId}-${minimum}`} value={{ max_tokens: Math.max(minimum, (cap ?? 200_000) + 200_000) }} minimum={minimum} submitLabel="增加额度并继续" onSave={async (v) => {
      if (!taskId || !v) throw new Error("找不到原任务");
      await budgetRequest(`/api/chat/${encodeURIComponent(taskId)}/budget/resume`, "POST", v);
      await onResolved?.();
    }} />
    <p className="text-body-xs text-ds-text-neutral-muted-default">仅调整本次任务的总额度。继续前请保持应用运行；重启后无法原位恢复。</p>
  </div>;
}
