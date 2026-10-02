import { create } from "zustand";
import { apiFetch } from "./backend";
import { normalizeSSEvent, type SSEvent } from "./sse";
import { useSessionsStore } from "@/store/sessions";
import { useSpacesStore } from "@/store/spaces";
import { getProjectRuntime } from "@/store/projectRuntime";
import { dispatchProjectEvent, getProjectTaskId, rememberProjectTaskId } from "@/store/livePark";
import { resolveEndMessageText, type Message } from "@/store/session";

export interface AppTask {
  task_id: string;
  status: string;
  text: string;
  updated_at: number;
  origin: { app_id: string; app_name: string; generation: string; project_id: string; space_id: string; route: string; context: Record<string, unknown>; parent_task_id?: string; dev_revision?: string };
  files?: Array<{ id: string; name: string }>;
  events?: Array<{ seq: number; event: Record<string, unknown> }>;
  waiting?: boolean;
  loaded_skills?: Array<{ id: string; name: string; version: string }>;
  storage_error?: string;
  recovery?: { cursor: number; end: Record<string, unknown> | null;
    pending_confirms: Record<string, unknown>[]; pending_questions: Record<string, unknown>[] };
  operations?: Array<{ operation_id: string; tool: string; status: string; result?: unknown; error?: string }>;
}

export const useAppTasks = create<{ records: Record<string, AppTask>; error: string }>(() => ({ records: {}, error: "" }));
const cursors = new Map<string, number>();
const started = new Set<string>();
const restored = new Set<string>();
const syncing = new Map<string, Promise<AppTask>>();
const cachedMessages = new Map<string, Message[]>();
export const isAppTaskRunning = (task: AppTask) => ["NEW", "RUNNING", "CANCELLING"].includes(task.status);

function terminalStatus(task: AppTask) {
  if (task.storage_error || ["FAILED", "INTERRUPTED"].includes(task.status)) return "error" as const;
  if (["DONE", "CANCELLED"].includes(task.status)) return "done" as const;
  return null;
}

function restoreTerminalStatus(task: AppTask) {
  const status = terminalStatus(task);
  const pid = task.origin.project_id;
  const bound = getProjectTaskId(pid);
  if (!status || (bound && bound !== task.task_id)) return;
  // Durable task status wins over a cached or replayed graph.start, even if
  // reading the rest of the history fails. Recovery never starts execution.
  getProjectRuntime(pid).session.setState({ runStatus: status, taskStartedAt: null,
    thinking: null, lastContentAt: null, lastBeatAt: null });
  useSessionsStore.getState().touchSession(pid, { status,
    updatedAt: useSessionsStore.getState().sessions.find(project => project.id === pid)?.updatedAt });
}

export async function appAIRequest<T>(appId: string, path: string, body?: unknown): Promise<T> {
  const base = await window.api.getBackendUrl();
  if (!base) throw new Error("后端未连接，请先配置模型");
  const response = await apiFetch(`${base}/api/industry-ai/${encodeURIComponent(appId)}${path}`, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `请求失败 (${response.status})`);
  return data as T;
}

function register(task: AppTask) {
  const origin = task.origin;
  const sessions = useSessionsStore.getState();
  const existing = sessions.sessions.find(project => project.id === origin.project_id);
  const updatedAt = task.updated_at > 0 ? task.updated_at * 1000 : existing?.updatedAt ?? Date.now();
  sessions.createProject(task.text.slice(0, 60), { id: origin.project_id, spaceId: origin.space_id, background: true,
    createdAt: existing?.createdAt ?? updatedAt, updatedAt,
    workdirMode: "artifact-only", appOrigin: { appId: origin.app_id, appName: origin.app_name, route: origin.route,
      taskId: task.task_id, generation: origin.generation } });
  sessions.touchSession(origin.project_id, { updatedAt, appOrigin: { appId: origin.app_id, appName: origin.app_name,
    route: origin.route, taskId: task.task_id, generation: origin.generation } });
  useAppTasks.setState(state => ({ records: { ...state.records, [task.task_id]: { ...state.records[task.task_id], ...task } } }));
}

export function syncAppTask(task: AppTask, options?: { recovery?: boolean }): Promise<AppTask> {
  const pending = syncing.get(task.task_id);
  if (pending) return pending;
  const work = (options?.recovery && !started.has(task.task_id) ? restoreRecord(task) : syncRecord(task))
    .finally(() => syncing.delete(task.task_id));
  syncing.set(task.task_id, work);
  return work;
}

async function restoreRecord(task: AppTask) {
  register(task);
  restoreTerminalStatus(task);
  const snapshot = await appAIRequest<AppTask>(task.origin.app_id, `/tasks/${task.task_id}?recovery=true`);
  const pid = task.origin.project_id;
  const runtime = getProjectRuntime(pid);
  const recordedAt = snapshot.updated_at > 0 ? snapshot.updated_at * 1000
    : useSessionsStore.getState().sessions.find(project => project.id === pid)!.updatedAt;
  const messages = [...(runtime.session.getState().messages.length
    ? runtime.session.getState().messages : useSessionsStore.getState().getMessages(pid))];
  let user = messages.findIndex(message => message.id === `app-user-${task.task_id}`);
  if (user < 0) user = messages.findIndex(message => message.role === "user" && message.content === task.text);
  if (user < 0) {
    user = messages.length;
    messages.push({id: `app-user-${task.task_id}`, role: "user", content: task.text, createdAt: recordedAt});
  }
  let end = messages.findIndex((message, index) => index > user && message.role === "user" && !message.humanReplyTo);
  if (end < 0) end = messages.length;
  const final = snapshot.recovery?.end ? normalizeSSEvent(snapshot.recovery.end).payload : {};
  const summary = resolveEndMessageText(String(final.summary || ""));
  const error = snapshot.storage_error || String(final.error || "");
  const content = summary || (error ? `任务失败：${error}` : "");
  if (content) {
    let answer = -1;
    for (let i = user + 1; i < end; i++) {
      const message = messages[i];
      if (message.role === "assistant" && !message.humanQuestion && !message.confirm && !message.memoryNotice) answer = i;
    }
    if (answer >= 0) {
      // Keep an interrupted partial answer when there is no final summary.
      const prior = messages[answer];
      messages[answer] = {...prior, content: summary || (prior.content.includes(content) ? prior.content : `${prior.content}\n${content}`)};
    } else {
      messages.splice(end, 0, {id: `app-answer-${task.task_id}`, role: "assistant", content, createdAt: recordedAt});
      end++;
    }
  }
  const settled = terminalStatus(snapshot);
  for (let i = user; i < end; i++) {
    const message = messages[i];
    messages[i] = {...message, createdAt: message.createdAt ? Math.min(message.createdAt, recordedAt) : recordedAt,
      ...(settled && message.humanQuestion?.status === "pending"
        ? {humanQuestion: {...message.humanQuestion, status: "cancelled" as const}} : {}),
      ...(settled && message.confirm?.status === "pending"
        ? {confirm: {...message.confirm, status: "expired" as const}} : {})};
  }
  rememberProjectTaskId(pid, task.task_id);
  runtime.session.setState({messages, trace: [], traceNodes: [], traceEdges: [], currentStepId: null,
    answerStreamByAgent: {}, confirmQueue: [], thinking: null, taskStartedAt: null, lastContentAt: null, lastBeatAt: null,
    runStatus: settled || "running"});
  // Only current unanswered requests are restored; old tool/LLM events stay on disk.
  if (!settled) {
    for (const request of snapshot.recovery?.pending_confirms || []) {
      dispatchProjectEvent(pid, normalizeSSEvent({...request, type: "tool.confirm_request", task_id: task.task_id}), {historical: true});
    }
    for (const question of snapshot.recovery?.pending_questions || []) {
      dispatchProjectEvent(pid, normalizeSSEvent({...question, type: "human.ask", task_id: task.task_id}), {historical: true});
    }
    runtime.session.setState({trace: [], traceNodes: [], traceEdges: []});
  }
  cursors.set(task.task_id, snapshot.recovery?.cursor || 0);
  started.add(task.task_id);
  restored.add(task.task_id);
  register(snapshot);
  restoreTerminalStatus(snapshot);
  useAppTasks.setState({error: ""});
  return snapshot;
}

async function syncRecord(task: AppTask) {
  register(task);
  const pid = task.origin.project_id;
  const runtime = getProjectRuntime(pid);
  restoreTerminalStatus(task);
  // Fetch every page before publishing history. Replaying graph.start between
  // network awaits made a completed task look live at 500 / 1000 events on boot.
  const events: Array<{ seq: number; event: SSEvent }> = [];
  let cursor = cursors.get(task.task_id) || 0;
  let snapshot: AppTask;
  do {
    snapshot = await appAIRequest<AppTask>(task.origin.app_id, `/tasks/${task.task_id}?after=${cursor}`);
    restoreTerminalStatus(snapshot);
    for (const row of snapshot.events || []) {
      events.push({ seq: row.seq, event: normalizeSSEvent(row.event) });
      cursor = row.seq;
    }
  } while (snapshot.events?.length === 500);
  if (!started.has(task.task_id)) {
    // Server execution records are authoritative; clear cached display once per project on recovery.
    if (![...started].some(id => useAppTasks.getState().records[id]?.origin.project_id === pid)) {
      cachedMessages.set(pid, runtime.session.getState().messages.length
        ? runtime.session.getState().messages : useSessionsStore.getState().getMessages(pid));
      runtime.session.setState({ messages: [] });
    }
    started.add(task.task_id);
    const cached = cachedMessages.get(pid)?.find(message => message.id === `app-user-${task.task_id}`)
      || cachedMessages.get(pid)?.find(message => message.role === "user" && message.content === task.text);
    const recordedAt = task.updated_at > 0 ? task.updated_at * 1000 : useSessionsStore.getState().sessions.find(project => project.id === pid)!.updatedAt;
    runtime.session.setState(state => ({ messages: [...state.messages, { id: `app-user-${task.task_id}`,
      role: "user", content: task.text, createdAt: cached?.createdAt ? Math.min(cached.createdAt, recordedAt) : recordedAt }] }));
    if (isAppTaskRunning(snapshot)) runtime.session.getState().beginRun();
    rememberProjectTaskId(pid, task.task_id);
  }
  const knownMessageIds = new Set(runtime.session.getState().messages.map(message => message.id));
  for (const row of events) {
    dispatchProjectEvent(pid, row.event, { historical: true });
    cursors.set(task.task_id, row.seq);
  }
  const status = terminalStatus(snapshot);
  const hasEnd = runtime.session.getState().trace.some(event => event.type === "graph.end" && event.payload.task_id === task.task_id);
  const unchangedRestoredEnd = restored.has(task.task_id) && !events.length && terminalStatus(task) === status;
  if (status && !unchangedRestoredEnd && (!hasEnd || runtime.session.getState().runStatus !== status)) {
    // Some interrupted/failed tasks have no persisted end event. Always settle
    // them from the snapshot, retaining any partial answer already recovered.
    dispatchProjectEvent(pid, { type: "graph.end", payload: { task_id: task.task_id,
      status: status === "error" ? "error" : snapshot.status === "CANCELLED" ? "cancelled" : "ok",
      error: snapshot.storage_error || (snapshot.status === "INTERRUPTED"
        ? "运行已中断。已完成的修改仍保留，请检查业务记录后再决定是否重新发起。" : "任务已结束，未保存结束事件。"),
    } }, { historical: true });
  }
  // Replaying durable events must not turn old messages into newly sent messages.
  const cached = cachedMessages.get(pid) || [];
  runtime.session.setState(state => ({ messages: state.messages.map(message => {
    if (knownMessageIds.has(message.id)) return message;
    const prior = cached.find(row => row.id === message.id || (row.role === message.role && row.content === message.content));
    const recordedAt = snapshot.updated_at > 0 ? snapshot.updated_at * 1000 : task.updated_at * 1000;
    return { ...message, createdAt: prior?.createdAt ? Math.min(prior.createdAt, recordedAt) : recordedAt };
  }) }));
  register(snapshot);
  restoreTerminalStatus(snapshot);
  useAppTasks.setState({ error: "" });
  return snapshot;
}

export async function startAppTask(appId: string, generation: string, input: Record<string, unknown>, requestId: string, parent?: AppTask) {
  const task = await appAIRequest<AppTask>(appId, "/tasks", {
    request_id: requestId, generation,
    project_id: parent?.origin.project_id || `app-${appId}-${requestId}`,
    space_id: parent?.origin.space_id || useSpacesStore.getState().activeSpaceId,
    prompt: input.prompt, context: input.context || {}, tools: input.tools || [], files: input.files || [],
    skills: input.skills || [],
    produce_file: input.produce_file === true, route: input.route || "", parent_task_id: parent?.task_id,
  });
  // Creation already succeeded; a display sync failure must not encourage a second execution.
  register(task);
  void syncAppTask(task).catch(error => useAppTasks.setState({ error: error instanceof Error ? error.message : String(error) }));
  return task;
}

export async function followupAppTask(projectId: string, prompt: string) {
  const project = useSessionsStore.getState().sessions.find(row => row.id === projectId);
  if (!project?.appOrigin) throw new Error("找不到业务来源");
  const origin = project.appOrigin;
  const parent = await appAIRequest<AppTask>(origin.appId, `/tasks/${origin.taskId}`);
  const status = await window.api.industryStatus();
  return startAppTask(origin.appId, status.generation || "", { prompt }, crypto.randomUUID(), parent);
}

/** One host-owned watcher survives iframe and workspace navigation. */
export function watchAppTasks() {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  let recovered = false;
  const tick = async () => {
    let error = "";
    try {
      let tasks = Object.values(useAppTasks.getState().records).filter(task =>
        isAppTaskRunning(task) || (task.status !== "INTERRUPTED" && task.operations?.some(operation => operation.status === "started")));
      if (!recovered) {
        const base = await window.api.getBackendUrl();
        const response = await apiFetch(`${base}/api/industry-ai-tasks`);
        if (!response.ok) throw new Error("AI 记录暂时无法读取");
        tasks = [...(await response.json() as { tasks: AppTask[] }).tasks].reverse();
      }
      const blockedProjects = new Set<string>();
      for (const task of tasks) {
        if (stopped) return;
        if (blockedProjects.has(task.origin.project_id)) continue;
        try { await syncAppTask(task, {recovery: !recovered}); }
        catch (failure) {
          error = failure instanceof Error ? failure.message : String(failure);
          blockedProjects.add(task.origin.project_id);
        }
      }
      if (!error) recovered = true;
    } catch (failure) { error = failure instanceof Error ? failure.message : String(failure); }
    useAppTasks.setState({ error });
    if (!stopped) timer = setTimeout(tick, 1000);
  };
  void tick();
  return () => { stopped = true; clearTimeout(timer); };
}
