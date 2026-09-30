import { apiFetch as fetch } from "@/api/backend";
import { BudgetResumePanel } from "../chat/TaskBudget";
import { backendUnavailableMessage } from "@/lib/backendStatus";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, CalendarClock, ChevronRight, Clock3, ExternalLink, Loader2, Pause, Play, Plus, RefreshCw, Trash2 } from "lucide-react";

import KeepAwakeBanner, { openKeepAwakeSettings } from "@/components/settings/KeepAwakeBanner";
import { Button } from "@/components/ui/button";
import MarkdownView from "@/components/chat/markdown/MarkdownView";
import { automationApi, type Automation, type AutomationRun, type RunEvent, type Schedule } from "@/api/automations";
import { useSessionsStore } from "@/store/sessions";
import { usePageTabStore } from "@/store/pageTab";
import { useSpacesStore } from "@/store/spaces";
import type { Message } from "@/store/session";

const card = "rounded-2xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default";
const input = "w-full rounded-xl border border-ds-border-neutral-strong-default bg-ds-bg-neutral-subtle-default px-3 py-2.5 text-sm text-ds-text-neutral-default-default outline-none focus-visible:ring-2 focus-visible:ring-ds-ring-neutral-subtle-default";
const label = "mb-1.5 block text-sm font-medium text-ds-text-neutral-default-default";

function fmt(value: number | null | undefined): string {
  return value ? new Date(value * 1000).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function statusName(value: string | null): string {
  return ({
    running: "运行中", waiting_user: "等待你的回复", ok: "已完成",
    error: "执行失败", skipped: "已跳过", interrupted: "已中断", cancelled: "已停止",
    recovery_review: "等待恢复确认",
  } as Record<string, string>)[value || ""] || "尚未运行";
}

function Status({ value }: { value: string | null }) {
  const tone = value === "ok" ? "text-emerald-700 bg-emerald-50" :
    value === "error" || value === "interrupted" ? "text-red-700 bg-red-50" :
    value === "running" || value === "waiting_user" || value === "recovery_review" ? "text-violet-700 bg-violet-100" :
    "text-ds-text-neutral-muted-default bg-ds-bg-neutral-subtle-default";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>{statusName(value)}</span>;
}

type FormState = {
  title: string; instructions: string; frequency: string; time: string;
  date: string; weekday: string; cron: string; timezone: string; interval: string;
};

function initialForm(task?: Automation): FormState {
  const schedule = task?.schedule;
  const cron = schedule?.cron || "";
  const match = cron.match(/^(\d+) (\d+) \* \* (\*|1-5|0,6|[0-6])$/);
  const frequency = schedule?.kind === "once" ? "once" :
    schedule?.kind === "interval" ? "interval" :
    match ? ({ "*": "daily", "1-5": "weekdays", "0,6": "weekends" } as Record<string, string>)[match[3]] || "weekly" : "custom";
  const fire = schedule?.fire_at || "";
  return {
    title: task?.title || "", instructions: task?.instructions || "",
    frequency: task ? frequency : "daily",
    time: match ? `${match[2].padStart(2, "0")}:${match[1].padStart(2, "0")}` : "09:00",
    date: fire.slice(0, 16), weekday: match && frequency === "weekly" ? match[3] : "1",
    cron, timezone: schedule?.timezone || "local",
    interval: String(schedule?.interval_seconds || 3600),
  };
}

function makeSchedule(form: FormState): Schedule {
  const timezone = form.timezone.trim() || "local";
  if (form.frequency === "once") return { kind: "once", fire_at: form.date, timezone };
  if (form.frequency === "interval") return { kind: "interval", interval_seconds: Number(form.interval), timezone };
  if (form.frequency === "custom") return { kind: "cron", cron: form.cron.trim(), timezone };
  const [hour, minute] = form.time.split(":").map(Number);
  const dow = form.frequency === "weekdays" ? "1-5" :
    form.frequency === "weekends" ? "0,6" :
    form.frequency === "weekly" ? form.weekday : "*";
  return { kind: "cron", cron: `${minute} ${hour} * * ${dow}`, timezone };
}

function TaskForm({ task, initial, busy, onCancel, onSubmit }: {
  task?: Automation; initial?: Partial<FormState>; busy: boolean; onCancel: () => void;
  onSubmit: (value: { title: string; instructions: string; schedule: Schedule; notify_on_completion: boolean; notify_target: string | null; permissions?: Array<{ tool: string; target: string; access: "write" }>; always_allowed_commands: string[]; auto_approve_commands: boolean }) => Promise<void>;
}) {
  const [form, setForm] = useState<FormState>(() => ({ ...initialForm(task), ...initial }));
  const [error, setError] = useState("");
  const [grants, setGrants] = useState<Array<{ tool: string; target: string; access: "write" }>>([]);
  const [grantTool, setGrantTool] = useState("browser_navigate");
  const [grantTarget, setGrantTarget] = useState("");
  const [commands, setCommands] = useState<string[]>(task?.always_allowed_commands || []);
  const [commandDraft, setCommandDraft] = useState("");
  const [autoApproveCommands, setAutoApproveCommands] = useState(task?.auto_approve_commands ?? false);
  const [notify, setNotify] = useState(task?.notify_on_completion ?? true);
  const [notifyTarget, setNotifyTarget] = useState(task?.notify_target?.replace(/^lark:/, "") || "");
  const update = (patch: Partial<FormState>) => setForm((current) => ({ ...current, ...patch }));
  return (
    <form className={`${card} p-5`} onSubmit={async (event) => {
      event.preventDefault();
      setError("");
      if (!form.title.trim() || !form.instructions.trim()) { setError("请填写任务名称和执行内容"); return; }
      if (form.frequency === "once" && !form.date) { setError("请选择执行日期和时间"); return; }
      try {
        await onSubmit({ title: form.title.trim(), instructions: form.instructions.trim(), schedule: makeSchedule(form), notify_on_completion: notify,
          notify_target: notify && notifyTarget.trim() ? `lark:${notifyTarget.trim().replace(/^lark:/, "")}` : null,
          always_allowed_commands: commands,
          auto_approve_commands: autoApproveCommands,
          ...(!task ? { permissions: grants } : {}) });
      } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
    }}>
      <div className="mb-4 flex items-center justify-between">
        <div className="text-base font-semibold text-ds-text-neutral-default-default">{task ? "编辑定时任务" : "新建定时任务"}</div>
        <Button type="button" variant="ghost" onClick={onCancel}>取消</Button>
      </div>
      <div className="grid gap-4">
        <div><label className={label} htmlFor="auto-title">任务名称</label>
          <input id="auto-title" className={input} value={form.title} onChange={(e) => update({ title: e.target.value })} placeholder="例如：每天整理行业新闻" required /></div>
        <div><label className={label} htmlFor="auto-instructions">执行内容</label>
          <textarea id="auto-instructions" className={`${input} min-h-28 resize-y`} value={form.instructions} onChange={(e) => update({ instructions: e.target.value })} placeholder="描述每次到点后需要完成的工作" required />
          <p className="mt-1 text-xs text-ds-text-neutral-muted-default">只写每次要执行的工作；执行时间在下方设置。</p></div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className={label} htmlFor="auto-frequency">执行频率</label>
            <select id="auto-frequency" className={input} value={form.frequency} onChange={(e) => update({ frequency: e.target.value })}>
              <option value="once">仅执行一次</option><option value="daily">每天</option>
              <option value="weekdays">工作日</option><option value="weekends">周末</option>
              <option value="weekly">每周</option><option value="interval">固定间隔</option>
              <option value="custom">自定义 Cron</option>
            </select></div>
          <div><label className={label} htmlFor="auto-timezone">时区</label>
            <input id="auto-timezone" className={input} value={form.timezone} onChange={(e) => update({ timezone: e.target.value })} placeholder="local 或 Asia/Shanghai" /></div>
        </div>
        {form.frequency === "once" ? <div><label className={label} htmlFor="auto-date">执行时间</label><input id="auto-date" type="datetime-local" className={input} value={form.date} onChange={(e) => update({ date: e.target.value })} required /></div> : null}
        {["daily", "weekdays", "weekends", "weekly"].includes(form.frequency) ? <div className="grid gap-3 sm:grid-cols-2">
          <div><label className={label} htmlFor="auto-time">每天的时间</label><input id="auto-time" type="time" className={input} value={form.time} onChange={(e) => update({ time: e.target.value })} /></div>
          {form.frequency === "weekly" ? <div><label className={label} htmlFor="auto-weekday">星期</label><select id="auto-weekday" className={input} value={form.weekday} onChange={(e) => update({ weekday: e.target.value })}>
            {["日", "一", "二", "三", "四", "五", "六"].map((day, index) => <option value={index} key={day}>星期{day}</option>)}
          </select></div> : null}
        </div> : null}
        {form.frequency === "interval" ? <div><label className={label} htmlFor="auto-interval">间隔秒数</label><input id="auto-interval" type="number" min="1" className={input} value={form.interval} onChange={(e) => update({ interval: e.target.value })} /></div> : null}
        {form.frequency === "custom" ? <div><label className={label} htmlFor="auto-cron">Cron 表达式</label><input id="auto-cron" className={input} value={form.cron} onChange={(e) => update({ cron: e.target.value })} placeholder="0 9 * * 1-5" /><p className="mt-1 text-xs text-ds-text-neutral-muted-default">分钟 小时 日期 月份 星期；例如 0 9 * * 1-5。</p></div> : null}
        <label className="flex cursor-pointer items-center gap-2 text-sm text-ds-text-neutral-default-default"><input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />完成后在应用内通知我</label>
        {notify ? <div><label className={label} htmlFor="auto-notify-target">同时发送到飞书（可选）</label><input id="auto-notify-target" className={input} value={notifyTarget} onChange={(e) => setNotifyTarget(e.target.value)} placeholder="飞书 chat_id" /><p className="mt-1 text-xs text-ds-text-neutral-muted-default">填入目标会话的 chat_id 后，任务成功时发送一条摘要。</p></div> : null}
        {!task ? <details className="rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default p-3 text-sm"><summary className="cursor-pointer font-medium">高级：固定目标授权</summary>
          <p className="my-2 text-xs text-ds-text-neutral-muted-default">仅对指定工具和完全匹配的目标生效。工作区内的交付文件可以直接写入；其他操作仍会询问你。</p>
          <div className="flex flex-wrap gap-2"><select aria-label="授权工具" className={`${input} max-w-44`} value={grantTool} onChange={(e) => setGrantTool(e.target.value)}>
            <option value="lark.send_message">飞书发送消息</option><option value="browser_navigate">浏览器打开网址</option><option value="fs.write">写入文件</option>
            <option value="docx.gen">生成 Word</option><option value="pptx.gen">生成 PPT</option>
            <option value="xlsx.gen">生成 Excel</option><option value="pdf.gen">生成 PDF</option>
          </select><input aria-label="授权目标" className={`${input} min-w-44 flex-1`} value={grantTarget} onChange={(e) => setGrantTarget(e.target.value)} placeholder={grantTool === "browser_navigate" ? "https://example.com/page" : grantTool === "lark.send_message" ? "飞书 chat_id" : "完整文件路径"} />
            <Button type="button" variant="outline" onClick={() => { if (!grantTarget.trim()) return; setGrants((items) => [...items, { tool: grantTool, target: grantTarget.trim(), access: "write" }]); setGrantTarget(""); }}>添加</Button></div>
          {grants.length ? <div className="mt-2 space-y-1">{grants.map((grant, index) => <div className="flex items-center gap-2 rounded-lg bg-ds-bg-brand-subtle-default px-2 py-1" key={`${grant.tool}-${grant.target}-${index}`}><span className="min-w-0 flex-1 truncate">{grant.tool} · {grant.target}</span><Button type="button" size="xs" variant="ghost" onClick={() => setGrants((items) => items.filter((_, row) => row !== index))}>移除</Button></div>)}</div> : null}
        </details> : null}
        <details className="rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default p-3 text-sm"><summary className="cursor-pointer font-medium">高级：执行授权{commands.length ? ` (${commands.length} 条命令)` : ""}</summary>
          <p className="my-2 text-xs text-ds-text-neutral-muted-default">仅当代理在此任务的工作区执行完全相同的命令时自动允许。不同命令仍会暂停询问；命令中的参数和路径也必须完全一致。</p>
          <label className="mb-3 flex cursor-pointer items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3"><input type="checkbox" className="mt-1" checked={autoApproveCommands} onChange={(event) => setAutoApproveCommands(event.target.checked)} /><span><strong className="block">自动批准此任务的命令与浏览器交互</strong><span className="mt-1 block text-xs text-amber-900">适用于无人值守运行；包括网页输入、点击、选择和上传。终端命令可访问工作区外的文件及网络，仅对你信任的任务开启。</span></span></label>
          <div className="flex flex-wrap gap-2"><input aria-label="允许的完整命令" className={`${input} min-w-44 flex-1 font-mono`} value={commandDraft} onChange={(e) => setCommandDraft(e.target.value)} placeholder="例如：git status --short" />
            <Button type="button" variant="outline" onClick={() => { const value = commandDraft.trim(); if (!value || commands.includes(value)) return; if (/[\x00-\x1f\x7f]/.test(value) || value.length > 2000) { setError("命令须为单行且不超过 2000 字符"); return; } setCommands((items) => [...items, value]); setCommandDraft(""); setError(""); }}>添加命令</Button></div>
          {commands.length ? <div className="mt-2 space-y-1">{commands.map((command) => <div className="flex items-center gap-2 rounded-lg bg-ds-bg-brand-subtle-default px-2 py-1" key={command}><code className="min-w-0 flex-1 break-all text-xs">{command}</code><Button type="button" size="xs" variant="ghost" onClick={() => setCommands((items) => items.filter((item) => item !== command))}>移除</Button></div>)}</div> : null}
        </details>
      </div>
      {error ? <p role="alert" className="mt-3 text-sm text-red-600">{error}</p> : null}
      <div className="mt-5 flex justify-end"><Button type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : null}{task ? "保存修改" : "创建任务"}</Button></div>
    </form>
  );
}

function eventData(event: RunEvent): Record<string, unknown> {
  return event.payload && typeof event.payload === "object" ? { ...event, ...(event.payload as Record<string, unknown>) } : event;
}

function PendingInput({ run, events, onResolved }: { run: AutomationRun; events: RunEvent[]; onResolved: () => Promise<void> }) {
  const pending = [...events].reverse().find((event) => ["human.ask", "tool.confirm_request", "to_sub_tasks", "budget.paused"].includes(event.type || ""));
  const data = pending ? eventData(pending) : null;
  const [answer, setAnswer] = useState("");
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!data || run.status !== "waiting_user") return null;
  if (pending?.type === "budget.paused") return <BudgetResumePanel taskId={run.task_execution_id} used={Number(data.tokens || 0)} cap={data.max_tokens === null ? null : Number(data.max_tokens || 200_000)} required={Number(data.required_tokens || 1)} onResolved={onResolved} />;
  const fields = Array.isArray(data.fields) ? data.fields as Array<{ label: string; kind: string; options?: string[]; required?: boolean }> : [];
  const options = Array.isArray(data.options) ? data.options.map(String) : [];
  const isQuestion = pending?.type === "human.ask";
  const isPlan = pending?.type === "to_sub_tasks";
  async function respond(allowed?: boolean, rememberCommand = false) {
    setBusy(true); setError("");
    try {
      if (isQuestion && fields.some((field) => field.required && !choices[field.label]?.trim())) {
        throw new Error("请先填写所有必填项");
      }
      const base = await window.api.getBackendUrl();
      if (!base) throw new Error(await backendUnavailableMessage());
      if (rememberCommand) {
        const command = (data?.args as Record<string, unknown> | undefined)?.cmd;
        if (data?.tool !== "exec.bash" || typeof command !== "string" || !command.trim()) throw new Error("无法保存这条命令");
        await automationApi(`/${encodeURIComponent(run.task_id)}`, { method: "PATCH", body: JSON.stringify({ add_command: command }) });
      }
      const content = fields.length
        ? fields.map((field) => `${field.label}：${choices[field.label] || ""}`).join("\n") + (answer.trim() ? `\n补充：${answer.trim()}` : "")
        : answer.trim();
      const url = isQuestion
        ? `${base}/api/chat/${encodeURIComponent(run.task_execution_id)}/human-reply`
        : isPlan ? `${base}/api/workforce/start`
          : `${base}/api/tool/confirm/${encodeURIComponent(String(data?.call_id || ""))}`;
      const response = await fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(isQuestion ? { question_id: data?.question_id, answer: content }
          : isPlan ? { task_id: run.task_execution_id, subtasks: data?.subtasks || [] }
            : { ok: allowed }),
      });
      if (!response.ok) throw new Error(`提交失败 (${response.status})`);
      setAnswer(""); await onResolved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "提交失败"); }
    finally { setBusy(false); }
  }
  return <div className={`${card} mt-4 p-4`}>
    <div className="mb-2 font-semibold text-ds-text-neutral-default-default">{isQuestion ? "需要你的回复" : isPlan ? "请确认执行方案" : "需要你的授权"}</div>
    {isQuestion ? <>
      <div className="mb-3 text-sm text-ds-text-neutral-default-default"><MarkdownView>{String(data.question || "")}</MarkdownView></div>
      {fields.map((field) => <div className="mb-3" key={field.label}><label className={label} htmlFor={`answer-${field.label}`}>{field.label}{field.required ? " *" : ""}</label>
        {field.kind === "single" && field.options?.length ? <select id={`answer-${field.label}`} className={input} value={choices[field.label] || ""} onChange={(e) => setChoices({ ...choices, [field.label]: e.target.value })}><option value="">请选择</option>{field.options.map((option) => <option key={option}>{option}</option>)}</select>
          : field.kind === "multiple" && field.options?.length ? <div className="grid gap-1.5 sm:grid-cols-2">{field.options.map((option) => {
            const selected = (choices[field.label] || "").split("、").filter(Boolean);
            return <label key={option} className="flex cursor-pointer items-center gap-2 rounded-lg border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default p-2 text-sm"><input type="checkbox" checked={selected.includes(option)} onChange={(event) => setChoices({ ...choices, [field.label]: (event.target.checked ? [...selected, option] : selected.filter((item) => item !== option)).join("、") })} />{option}</label>;
          })}</div>
          : <input id={`answer-${field.label}`} className={input} value={choices[field.label] || ""} onChange={(e) => setChoices({ ...choices, [field.label]: e.target.value })} />}</div>)}
      {!fields.length && options.length ? <div className="mb-3 flex flex-wrap gap-2">{options.map((option) => <Button type="button" key={option} variant={answer === option ? "primary" : "outline"} onClick={() => setAnswer(option)}>{option}</Button>)}</div> : null}
      <label className={label} htmlFor="run-answer">{fields.length ? "补充说明" : "你的回答"}</label>
      <textarea id="run-answer" className={`${input} min-h-20`} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="也可以自行填写" />
      <div className="mt-3"><Button disabled={busy || (!answer.trim() && !Object.values(choices).some(Boolean))} onClick={() => void respond()}>提交并继续</Button></div>
    </> : isPlan ? <>
      <div className="mb-3 space-y-2">{(Array.isArray(data.subtasks) ? data.subtasks : []).map((step, index) => <div key={index} className="rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default p-3 text-sm">{index + 1}. {String((step as Record<string, unknown>).title || (step as Record<string, unknown>).description || "执行步骤")}</div>)}</div>
      <Button disabled={busy} onClick={() => void respond()}>确认方案并继续</Button>
    </> : <>
      <p className="mb-2 text-sm">{String(data.tool || "工具调用")}</p>
      <pre className="mb-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-ds-bg-neutral-subtle-default p-3 text-xs">{JSON.stringify(data.args || {}, null, 2)}</pre>
      <div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => void respond(true)}>本次允许</Button>{data.tool === "exec.bash" ? <Button disabled={busy} variant="outline" onClick={() => void respond(true, true)}>此任务以后允许这条命令</Button> : null}<Button disabled={busy} variant="outline" onClick={() => void respond(false)}>拒绝</Button></div>
    </>}
    {error ? <p role="alert" className="mt-2 text-sm text-red-600">{error}</p> : null}
  </div>;
}

export default function ScheduleView({ search = "" }: { search?: string } = {}) {
  const [tasks, setTasks] = useState<Automation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ task: Automation; runs: AutomationRun[] } | null>(null);
  const [runDetail, setRunDetail] = useState<{ run: AutomationRun; events: RunEvent[] } | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [draft, setDraft] = useState<Partial<FormState> | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const createProject = useSessionsStore((state) => state.createProject);
  const setWorkspaceView = usePageTabStore((state) => state.setWorkspaceView);

  const refresh = useCallback(async () => {
    try {
      const list = await automationApi<{ tasks: Automation[] }>("");
      setTasks(list.tasks);
      if (selectedId) {
        const next = await automationApi<{ task: Automation; runs: AutomationRun[] }>(`/${encodeURIComponent(selectedId)}`);
        setDetail(next);
        if (selectedRunId) {
          const run = await automationApi<{ run: AutomationRun; events: RunEvent[] }>(`/${encodeURIComponent(selectedId)}/runs/${encodeURIComponent(selectedRunId)}`);
          setRunDetail(run);
        }
      }
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
  }, [selectedId, selectedRunId]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function mutate(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "操作失败"); }
    finally { setBusy(false); }
  }

  const openTask = async (id: string) => {
    setSelectedId(id); setSelectedRunId(null); setRunDetail(null); setFormOpen(false);
    try {
      const next = await automationApi<{ task: Automation; runs: AutomationRun[] }>(`/${encodeURIComponent(id)}`);
      setDetail(next);
      await automationApi(`/${encodeURIComponent(id)}/seen`, { method: "POST" });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
  };
  const openRun = async (id: string) => {
    if (!selectedId) return;
    setSelectedRunId(id);
    try { setRunDetail(await automationApi(`/${encodeURIComponent(selectedId)}/runs/${encodeURIComponent(id)}`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
  };

  function continueRun(run: AutomationRun) {
    if (!detail) return;
    const spaceStore = useSpacesStore.getState();
    const workspace = detail.task.workspace;
    const spaceId = workspace
      ? spaceStore.spaces.find((space) => space.rootPath === workspace)?.id ||
        spaceStore.createFolderSpace(`自动化 · ${detail.task.title}`, workspace)
      : detail.task.space_id || undefined;
    const messages: Message[] = [
      { id: `${run.run_id}-ask`, role: "user", content: detail.task.instructions, createdAt: run.started_at * 1000 },
      { id: `${run.run_id}-answer`, role: "assistant", content: run.result_text || run.error || statusName(run.status), createdAt: (run.finished_at || run.started_at) * 1000 },
    ];
    createProject(detail.task.title, {
      id: run.session_id, initialMessages: messages,
      spaceId, workdirMode: workspace ? "direct-write" : undefined,
      assistantId: detail.task.assistant_id || undefined,
    });
    setWorkspaceView("workspace");
  }

  const currentTask = detail?.task;
  return <div className="w-full overflow-y-auto px-4 pb-8">
    <div className="sticky top-0 z-10 mb-4 flex items-center justify-between border-b border-ds-border-neutral-subtle-default bg-[var(--ui-card-bg)] py-3">
      <div className="flex items-center gap-2">
        {selectedId ? <Button variant="ghost" size="icon" aria-label="返回任务列表" onClick={() => { setSelectedId(null); setSelectedRunId(null); setDetail(null); setRunDetail(null); setEditing(false); }}><ArrowLeft /></Button> : <CalendarClock className="size-5 text-ds-text-brand-default-default" />}
        <div><h2 className="text-base font-bold text-ds-text-neutral-default-default">{currentTask?.title || "定时任务"}</h2><p className="text-xs text-ds-text-neutral-muted-default">{selectedId ? "任务详情与运行记录" : "让代理按你的计划自动完成工作"}</p></div>
      </div>
      <div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => void refresh()} aria-label="刷新定时任务"><RefreshCw /></Button>
        {!selectedId ? <Button size="sm" onClick={() => setFormOpen((value) => !value)}><Plus /> 新建</Button> : null}</div>
    </div>
    <KeepAwakeBanner className="mb-4" message="任务在电脑唤醒、后端运行时执行；重新启动后会补执行错过的计划一次。" onOpenKeepAwake={openKeepAwakeSettings} />
    {error ? <div role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

    {!selectedId ? <div className="space-y-3">
      {formOpen ? <TaskForm key={JSON.stringify(draft)} initial={draft || undefined} busy={busy} onCancel={() => { setFormOpen(false); setDraft(null); }} onSubmit={async (value) => {
        await mutate(async () => {
          const response = await automationApi<{ task: Automation }>("", { method: "POST", body: JSON.stringify(value) });
          setFormOpen(false); await openTask(response.task.id);
        });
      }} /> : null}
      {tasks.length ? tasks.filter((task) => `${task.title} ${task.instructions}`.toLowerCase().includes(search.toLowerCase())).map((task) => <button type="button" key={task.id} onClick={() => void openTask(task.id)} className={`${card} flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-violet-300 focus-visible:outline-2 focus-visible:outline-violet-500`}>
        <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-100 text-violet-700"><Clock3 className="size-5" /></div>
        <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="truncate font-semibold text-ds-text-neutral-default-default">{task.title}</span>{task.unseen_runs ? <span className="rounded-full bg-violet-600 px-1.5 text-xs text-white">{task.unseen_runs}</span> : null}</div>
          <p className="truncate text-xs text-ds-text-neutral-muted-default">{task.enabled ? task.schedule_label : "已暂停"} · 下次 {fmt(task.next_run)} · 已运行 {task.run_count} 次</p></div>
        <Status value={task.last_status} /><ChevronRight className="size-4 text-ds-text-neutral-muted-default" />
      </button>) : !formOpen ? <div className="space-y-4"><div className={`${card} flex flex-col items-center gap-3 p-8 text-center`}><CalendarClock className="size-9 text-violet-500" /><div className="font-semibold">还没有定时任务</div><p className="text-sm text-ds-text-neutral-muted-default">创建一个任务，设置执行内容和时间。</p><Button onClick={() => setFormOpen(true)}><Plus /> 新建定时任务</Button></div>
        <div><div className="mb-2 text-sm font-semibold">从常见任务开始</div><div className="grid gap-2 sm:grid-cols-3">{[
          { title: "每日资讯简报", instructions: "搜索今天的重要资讯，核实来源并整理成简明摘要。", frequency: "daily", time: "09:00" },
          { title: "每周工作总结", instructions: "整理本周工作记录，归纳进展、待办和下周计划。", frequency: "weekly", weekday: "5", time: "17:00" },
          { title: "每日待办整理", instructions: "查看当前工作区的待办，整理今天最重要的事项。", frequency: "weekdays", time: "08:30" },
        ].map((template) => <button type="button" key={template.title} className={`${card} p-3 text-left text-sm transition-colors hover:border-violet-300`} onClick={() => { setDraft(template); setFormOpen(true); }}><div className="font-semibold">{template.title}</div><div className="mt-1 line-clamp-2 text-xs text-ds-text-neutral-muted-default">{template.instructions}</div></button>)}</div></div>
      </div> : null}
    </div> : currentTask ? <div className="space-y-4">
      <div className={`${card} p-5`}>
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-wide text-ds-text-brand-default-default">{currentTask.source === "skill" ? "技能计划" : "自动化任务"}</div><div className="mt-1 text-lg font-bold">{currentTask.title}</div></div><Status value={currentTask.last_status} /></div>
        <p className="whitespace-pre-wrap text-sm leading-6 text-ds-text-neutral-default-default">{currentTask.instructions}</p>
        <div className="mt-4 grid gap-2 border-t border-ds-border-neutral-subtle-default pt-3 text-sm text-ds-text-neutral-muted-default sm:grid-cols-2"><span>计划：{currentTask.schedule_label}</span><span>时区：{currentTask.schedule.timezone}</span><span>下次运行：{fmt(currentTask.next_run)}</span><span>上次运行：{fmt(currentTask.last_run)}</span></div>
        {currentTask.notify_target ? <p className="mt-2 text-xs text-ds-text-neutral-muted-default">完成通知：{currentTask.notify_target}</p> : null}
        {currentTask.auto_approve_commands ? <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">已开启自动批准命令与浏览器交互：此任务运行时无需逐条确认这些操作。</p> : null}
        {currentTask.always_allowed_tools?.length ? <div className="mt-3 border-t border-ds-border-neutral-subtle-default pt-3"><div className="mb-2 text-xs font-semibold text-ds-text-neutral-muted-default">无需再次确认的固定目标</div>
          <div className="space-y-1">{currentTask.always_allowed_tools.map((grant) => <div className="flex items-center gap-2 text-xs" key={`${grant.tool}-${grant.target}`}><span className="min-w-0 flex-1 truncate">{grant.tool} · {grant.target}</span><Button size="xs" variant="ghost" disabled={busy} onClick={() => void mutate(() => automationApi(`/${encodeURIComponent(currentTask.id)}`, { method: "PATCH", body: JSON.stringify({ revoke_permission: `${grant.tool} ${grant.target}` }) }))}>撤销</Button></div>)}</div>
        </div> : null}
        {currentTask.always_allowed_commands?.length ? <div className="mt-3 border-t border-ds-border-neutral-subtle-default pt-3"><div className="mb-2 text-xs font-semibold text-ds-text-neutral-muted-default">自动执行的完整命令（仅此任务工作区）</div>
          <div className="space-y-1">{currentTask.always_allowed_commands.map((command) => <div className="flex items-center gap-2 text-xs" key={command}><code className="min-w-0 flex-1 break-all">{command}</code><Button size="xs" variant="ghost" disabled={busy} onClick={() => void mutate(() => automationApi(`/${encodeURIComponent(currentTask.id)}`, { method: "PATCH", body: JSON.stringify({ revoke_command: command }) }))}>撤销</Button></div>)}</div>
        </div> : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => void mutate(async () => {
            const result = await automationApi<{ run: AutomationRun }>(`/${encodeURIComponent(currentTask.id)}/run`, { method: "POST" });
            await openRun(result.run.run_id);
          })}><Play /> 立即运行</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing((value) => !value)}>编辑</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void mutate(() => automationApi(`/${encodeURIComponent(currentTask.id)}`, { method: "PATCH", body: JSON.stringify({ enabled: !currentTask.enabled }) }))}>{currentTask.enabled ? <Pause /> : <Play />}{currentTask.enabled ? "暂停" : "恢复"}</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => {
            if (!window.confirm(`删除“${currentTask.title}”及其运行记录？`)) return;
            void mutate(async () => {
              await automationApi(`/${encodeURIComponent(currentTask.id)}`, { method: "DELETE" });
              setSelectedId(null); setDetail(null); setSelectedRunId(null); setRunDetail(null);
            });
          }}><Trash2 /> 删除</Button>
        </div>
      </div>
      {editing ? <TaskForm task={currentTask} busy={busy} onCancel={() => setEditing(false)} onSubmit={async (value) => {
        await mutate(async () => {
          await automationApi(`/${encodeURIComponent(currentTask.id)}`, { method: "PATCH", body: JSON.stringify(value) });
          setEditing(false);
        });
      }} /> : null}
      <div className={`${card} p-5`}>
        <div className="mb-3 font-semibold">运行记录</div>
        {detail.runs.length ? <div className="space-y-2">{detail.runs.map((run) => <button type="button" key={run.run_id} onClick={() => void openRun(run.run_id)} className={`flex w-full items-center justify-between gap-3 rounded-xl border p-3 text-left transition-colors hover:border-violet-300 ${selectedRunId === run.run_id ? "border-violet-400 bg-ds-bg-brand-subtle-default" : "border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default"}`}>
          <div><div className="text-sm font-medium">{fmt(run.started_at)}</div><div className="text-xs text-ds-text-neutral-muted-default">{run.trigger === "manual" ? "手动运行" : run.trigger === "catchup" ? "启动补执行" : "按计划运行"}</div></div><Status value={run.status} />
        </button>)}</div> : <p className="text-sm text-ds-text-neutral-muted-default">尚无运行记录。</p>}
      </div>
      {runDetail ? <div className={`${card} p-5`}>
        <div className="mb-3 flex items-center justify-between"><div><div className="font-semibold">本次运行</div><div className="text-xs text-ds-text-neutral-muted-default">{fmt(runDetail.run.started_at)} · {statusName(runDetail.run.status)}</div></div>
          {["ok", "error", "interrupted", "cancelled"].includes(runDetail.run.status) ? <Button size="sm" variant="outline" onClick={() => continueRun(runDetail.run)}><ExternalLink /> 进入会话追问</Button>
            : ["running", "waiting_user", "recovery_review"].includes(runDetail.run.status) ? <Button size="sm" variant="outline" disabled={busy} onClick={() => void mutate(() => automationApi(`/${encodeURIComponent(currentTask.id)}/runs/${encodeURIComponent(runDetail.run.run_id)}/cancel`, { method: "POST" }))}>停止运行</Button> : null}</div>
        {runDetail.run.status === "recovery_review" ? <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><div className="font-semibold">恢复前请检查上次操作</div><p className="mt-1">后端退出时，下列工具正在执行，无法确认外部操作是否已完成。请先检查目标文件或消息，再决定是否重试。</p><ul className="mt-2 list-disc pl-5">{(runDetail.run.recovery_tools || []).map((item) => <li key={item.call_id}>{item.tool}</li>)}</ul><Button className="mt-3" disabled={busy} onClick={() => void mutate(() => automationApi(`/${encodeURIComponent(currentTask.id)}/runs/${encodeURIComponent(runDetail.run.run_id)}/resume`, { method: "POST" }))}>我已检查，继续重试</Button></div> : null}
        {runDetail.run.result_text ? <div className="prose prose-sm max-w-none rounded-xl bg-ds-bg-neutral-subtle-default p-4"><MarkdownView>{runDetail.run.result_text}</MarkdownView></div> : null}
        {runDetail.run.error ? <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{runDetail.run.error}</p> : null}
        {runDetail.run.notification_error ? <p className="mt-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">任务已完成，但飞书通知失败：{runDetail.run.notification_error}</p> : null}
        {runDetail.run.artifacts.length ? <div className="mt-3 text-sm"><div className="mb-1 font-medium">交付文件</div>{runDetail.run.artifacts.map((path) => <div key={path} className="break-all text-ds-text-brand-default-default">{path}</div>)}</div> : null}
        <PendingInput run={runDetail.run} events={runDetail.events} onResolved={refresh} />
        {!runDetail.run.result_text && !runDetail.run.error && !["waiting_user", "recovery_review"].includes(runDetail.run.status) ? <p className="text-sm text-ds-text-neutral-muted-default">代理正在执行，完成后结果会显示在这里。</p> : null}
      </div> : null}
    </div> : null}
  </div>;
}
