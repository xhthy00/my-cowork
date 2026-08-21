/**
 * Per-project stream routing — Eigent-aligned.
 * Each project owns a live store; SSE never swaps another chat into the
 * active UI. Switching sessions does not abort in-flight streams.
 */
import type { SSEvent } from "../api/sse";
import {
  dropProjectRuntime,
  ensureProjectRuntime,
  getProjectRuntime,
  peekProjectRuntime,
  setActiveProjectRuntime,
} from "./projectRuntime";
import { type Message } from "./session";
import { useSessionsStore } from "./sessions";

const taskIdByProject = new Map<string, string>();

export function getProjectTaskId(projectId: string): string | undefined {
  return taskIdByProject.get(projectId);
}

export function rememberProjectTaskId(projectId: string, taskId: string): void {
  if (projectId && taskId) taskIdByProject.set(projectId, taskId);
}

export function dropProjectPark(projectId: string): void {
  dropProjectRuntime(projectId);
  taskIdByProject.delete(projectId);
}

export function parkProject(projectId: string): void {
  if (!projectId) return;
  const rt = peekProjectRuntime(projectId);
  if (!rt) return;
  useSessionsStore.getState().saveMessages(projectId, rt.session.getState().messages);
}

export function restoreProject(
  projectId: string,
  fallbackMessages: Message[],
): void {
  setActiveProjectRuntime(projectId);
  ensureProjectRuntime(projectId, fallbackMessages);
}

export function dispatchProjectEvent(projectId: string, event: SSEvent): void {
  const tid = event.payload?.task_id;
  if (typeof tid === "string" && tid) {
    const bound = taskIdByProject.get(projectId);
    if (bound && bound !== tid) return;
    rememberProjectTaskId(projectId, tid);
  }

  getProjectRuntime(projectId).session.getState().handleEvent(event, projectId);

  if (event.type === "graph.start") {
    useSessionsStore.getState().touchSession(projectId, { status: "running" });
  }
  if (event.type === "graph.end") {
    useSessionsStore.getState().touchSession(projectId, {
      status: event.payload.status === "error" ? "error" : "done",
    });
  }
}
