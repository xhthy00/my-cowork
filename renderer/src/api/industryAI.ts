import { create } from "zustand";
import { apiFetch } from "./backend";
import { normalizeSSEvent } from "./sse";
import { useSessionsStore } from "@/store/sessions";
import { useSpacesStore } from "@/store/spaces";
import { getProjectRuntime } from "@/store/projectRuntime";
import { dispatchProjectEvent, rememberProjectTaskId } from "@/store/livePark";

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
  operations?: Array<{ operation_id: string; tool: string; status: string; result?: unknown; error?: string }>;
}

export const useAppTasks = create<{ records: Record<string, AppTask>; error: string }>(() => ({ records: {}, error: "" }));
const cursors = new Map<string, number>();
const started = new Set<string>();
const syncing = new Map<string, Promise<AppTask>>();
export const isAppTaskRunning = (task: AppTask) => ["NEW", "RUNNING", "PAUSED", "CANCELLING"].includes(task.status);

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
  sessions.createProject(task.text.slice(0, 60), { id: origin.project_id, spaceId: origin.space_id, background: true,
    workdirMode: "artifact-only", appOrigin: { appId: origin.app_id, appName: origin.app_name, route: origin.route,
      taskId: task.task_id, generation: origin.generation } });
  useAppTasks.setState(state => ({ records: { ...state.records, [task.task_id]: { ...state.records[task.task_id], ...task } } }));
}

export function syncAppTask(task: AppTask): Promise<AppTask> {
  const pending = syncing.get(task.task_id);
  if (pending) return pending;
  const work = syncRecord(task).finally(() => syncing.delete(task.task_id));
  syncing.set(task.task_id, work);
  return work;
}

async function syncRecord(task: AppTask) {
  register(task);
  const pid = task.origin.project_id;
  const runtime = getProjectRuntime(pid);
  if (!started.has(task.task_id)) {
    // Server execution records are authoritative; clear cached display once per project on recovery.
    if (![...started].some(id => useAppTasks.getState().records[id]?.origin.project_id === pid)) {
      runtime.session.setState({ messages: [] });
    }
    started.add(task.task_id);
    runtime.session.getState().addUserMessage(task.text);
    runtime.session.getState().beginRun();
    rememberProjectTaskId(pid, task.task_id);
    useSessionsStore.getState().touchSession(pid, { appOrigin: { appId: task.origin.app_id, appName: task.origin.app_name,
      route: task.origin.route, taskId: task.task_id, generation: task.origin.generation } });
  }
  let snapshot: AppTask;
  do {
    snapshot = await appAIRequest<AppTask>(task.origin.app_id, `/tasks/${task.task_id}?after=${cursors.get(task.task_id) || 0}`);
    for (const row of snapshot.events || []) {
      dispatchProjectEvent(pid, normalizeSSEvent(row.event));
      cursors.set(task.task_id, row.seq);
    }
  } while (snapshot.events?.length === 500);
  if (snapshot.storage_error || snapshot.status === "INTERRUPTED") {
    dispatchProjectEvent(pid, { type: "graph.end", payload: { task_id: task.task_id, status: "error", error: snapshot.storage_error || "运行已中断。已完成的修改仍保留，请检查业务记录后再决定是否重新发起。" } });
  }
  register(snapshot);
  useAppTasks.setState({ error: "" });
  return snapshot;
}

export async function startAppTask(appId: string, generation: string, input: Record<string, unknown>, requestId: string, parent?: AppTask) {
  const project = parent && useSessionsStore.getState().sessions.find(row => row.id === parent.origin.project_id);
  const reasoning = project?.modelProfileId ? project.modelReasoning?.[project.modelProfileId] : undefined;
  const task = await appAIRequest<AppTask>(appId, "/tasks", {
    request_id: requestId, generation,
    project_id: parent?.origin.project_id || `app-${appId}-${requestId}`,
    space_id: parent?.origin.space_id || useSpacesStore.getState().activeSpaceId,
    prompt: input.prompt, context: input.context || {}, tools: input.tools || [], files: input.files || [],
    skills: input.skills || [],
    produce_file: input.produce_file === true, route: input.route || "", parent_task_id: parent?.task_id,
    model_profile_id: project?.modelProfileId,
    reasoning: reasoning ? { ...(reasoning.effort !== undefined ? { effort: reasoning.effort } : {}), ...(reasoning.budgetTokens !== undefined ? { budgetTokens: reasoning.budgetTokens } : {}) } : undefined,
    task_budget: project?.taskBudget,
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
        try { await syncAppTask(task); }
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
