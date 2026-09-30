import { useEffect, useRef, useState } from "react";
import { useStore } from "zustand";
import { X, ArrowLeft, ArrowUpRight } from "lucide-react";
import { appAIRequest, isAppTaskRunning, useAppTasks, type AppTask } from "@/api/industryAI";
import { getProjectRuntime } from "@/store/projectRuntime";
import { useSessionsStore } from "@/store/sessions";
import { usePageTabStore } from "@/store/pageTab";
import { leaveIndustryPage } from "@/store/industryNavigation";
import ChatConfirmCard from "../chat/ChatConfirmCard";
import HumanQuestionCard from "../chat/HumanQuestionCard";
import MessageContent from "../chat/MessageContent";
import { Button } from "../ui/button";

export async function openAppFile(appId: string, fileId: string) {
  const file = await appAIRequest<{ path: string; name: string }>(appId, `/files/${encodeURIComponent(fileId)}`);
  await window.api.ipcOpenPath(file.path);
}

export function expandAppTask(task: AppTask) {
  if (!leaveIndustryPage()) return;
  useSessionsStore.getState().setActive(task.origin.project_id);
  usePageTabStore.getState().setWorkspaceView("workspace");
}

const STATUS: Record<string, string> = { NEW: "准备中", RUNNING: "进行中", CANCELLING: "停止处理中", DONE: "已完成", FAILED: "执行失败", CANCELLED: "已停止", INTERRUPTED: "已中断" };

function TaskDetail({ task }: { task: AppTask }) {
  const records = useAppTasks(state => state.records);
  const related = Object.values(records).filter(record => record.origin.project_id === task.origin.project_id);
  const messages = useStore(getProjectRuntime(task.origin.project_id).session, state => state.messages);
  const [error, setError] = useState("");
  const [stopping, setStopping] = useState(false);
  const active = isAppTaskRunning(task);
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="shrink-0 border-b border-ds-border-neutral-subtle-default px-4 py-3">
      <p className="m-0 text-sm font-medium">{task.text}</p>
      <p className="mb-0 mt-1 text-xs text-ds-text-neutral-muted-default">{task.origin.app_name} · {task.waiting ? "待处理" : STATUS[task.status] || task.status} · {new Date(task.updated_at * 1000).toLocaleString()}</p>
      {!!task.loaded_skills?.length && <p className="mb-0 mt-1 text-xs text-ds-text-neutral-muted-default" title={task.loaded_skills.map(skill => `${skill.name}（${skill.version}）`).join("、")}>本次载入技能：{task.loaded_skills.map(skill => skill.name).join("、")}</p>}
      <details className="app-details mt-2 text-xs"><summary>任务详情</summary>
        {task.origin.dev_revision && <p className="break-all">开发修订：{task.origin.dev_revision}</p>}
        <p className="mb-0">本次业务范围</p><pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(task.origin.context, null, 2)}</pre>
      </details>
    </div>
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
      {messages.filter(message => message.role === "assistant").map(message => message.humanQuestion
        ? <HumanQuestionCard key={message.id} projectId={task.origin.project_id} question={message.humanQuestion} text={message.content} />
        : message.confirm ? (message.confirm.status === "pending" && active
          ? <ChatConfirmCard key={message.id} projectId={task.origin.project_id} confirm={message.confirm} />
          : <p key={message.id} className="text-sm">{message.confirm.status === "allowed" ? "已允许操作" : message.confirm.status === "denied" ? "已拒绝操作" : "确认已结束"}</p>)
        : message.content ? <MessageContent key={message.id} content={message.content} role="assistant" /> : null)}
      {!messages.some(message => message.role === "assistant" && (message.content || message.confirm?.status === "pending" || message.humanQuestion?.status === "pending")) && active && <p role="status" className="text-sm text-ds-text-neutral-muted-default">正在处理，可收起此面板继续业务工作。</p>}
      {related.flatMap(record => record.files || []).map(file => <Button key={file.id} variant="outline" size="sm" onClick={() => { void openAppFile(task.origin.app_id, file.id).catch(error => setError(error.message)); }}>{file.name}</Button>)}
      {related.flatMap(record => record.operations || []).map(operation => <div key={operation.operation_id} className="rounded-lg border border-ds-border-neutral-subtle-default p-3 text-sm">
        <p className="m-0 font-medium">{operation.tool} · {({ started: "尚未收到执行结果", completed: "已返回结果", failed: "执行失败", interrupted: "已中断，需检查实际记录" } as Record<string, string>)[operation.status]}</p>
        {operation.result !== undefined && <details className="app-details mt-2 text-xs"><summary>执行详情</summary><pre className="mb-0 max-h-40 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(operation.result, null, 2)}</pre></details>}
        {operation.error && <p>{operation.error}</p>}
      </div>)}
      {["CANCELLED", "INTERRUPTED"].includes(task.status) && <p className="text-sm">{STATUS[task.status]}。已经完成的操作不会撤销，请检查业务记录；尚未返回结果的操作不能视为未生效。</p>}
      {error && <p role="alert" className="text-sm text-ds-text-error-default-default">{error}</p>}
    </div>
    <div className="flex shrink-0 items-center justify-between gap-2 border-t border-ds-border-neutral-subtle-default p-3">
      <Button variant="outline" size="sm" onClick={() => expandAppTask(task)}><ArrowUpRight className="size-4" />展开与追问</Button>
      {active && <Button variant="ghost" size="sm" disabled={stopping} onClick={() => {
        setStopping(true); setError("");
        void appAIRequest(task.origin.app_id, `/tasks/${task.task_id}/cancel`, {}).catch(error => { setError(error.message); setStopping(false); });
      }}>{stopping ? "停止处理中…" : "停止任务"}</Button>}
    </div>
  </div>;
}

export default function IndustryAIPanel({ appId, selectedId, onSelect, onClose }: {
  appId: string; selectedId: string | null; onSelect: (id: string | null) => void; onClose: () => void;
}) {
  const records = useAppTasks(state => state.records);
  const error = useAppTasks(state => state.error);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => previous?.focus();
  }, []);
  useEffect(() => { closeRef.current?.focus(); }, [selectedId]);
  const all = Object.values(records).filter(task => task.origin.app_id === appId).sort((a, b) => b.updated_at - a.updated_at);
  const tasks = all.filter((task, index) => all.findIndex(row => row.origin.project_id === task.origin.project_id) === index);
  const selected = tasks.find(task => task.origin.project_id === (selectedId ? records[selectedId]?.origin.project_id : undefined));
  return <aside aria-label="AI 记录" className="absolute inset-y-0 right-0 z-20 flex w-full flex-col border-l border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default shadow-xl sm:w-[min(30rem,100%)]" onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    <header className="flex min-h-12 shrink-0 items-center gap-2 border-b border-ds-border-neutral-subtle-default px-3">
      {selected && <Button variant="ghost" size="icon" aria-label="返回 AI 记录列表" onClick={() => onSelect(null)}><ArrowLeft className="size-4" /></Button>}
      <h3 className="m-0 flex-1 text-sm font-semibold">AI 记录</h3>
      <Button ref={closeRef} variant="ghost" size="icon" aria-label="收起 AI 记录" onClick={onClose}><X className="size-4" /></Button>
    </header>
    {error && <p role="alert" className="px-4 text-sm text-ds-text-error-default-default">{error}</p>}
    {selected ? <TaskDetail task={selected} /> : <div className="min-h-0 flex-1 overflow-y-auto p-3">
      {tasks.length ? tasks.map(task => <button key={task.task_id} className="mb-2 block w-full rounded-lg border border-ds-border-neutral-subtle-default p-3 text-left hover:bg-ds-bg-neutral-subtle-default" onClick={() => onSelect(task.task_id)}>
        <span className="block truncate text-sm font-medium">{task.text}</span><span className="mt-1 block text-xs text-ds-text-neutral-muted-default">{task.waiting ? "待处理" : STATUS[task.status]} · {new Date(task.updated_at * 1000).toLocaleString()}</span>
      </button>) : <p className="p-2 text-sm text-ds-text-neutral-muted-default">从业务页面发起分析或生成报告后，可在这里找回。</p>}
    </div>}
  </aside>;
}
