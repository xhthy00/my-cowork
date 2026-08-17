/**
 * Per-project live UI park — Eigent-aligned: switch sessions without aborting SSE.
 * Single live store; background projects keep a memory snapshot updated via applyToProject.
 */
import type { SSEvent } from "../api/sse";
import { usePreviewStore, type SessionPreviewTab } from "./preview";
import {
  useSessionStore,
  type ConfirmRequest,
  type FileArtifact,
  type Message,
  type RunStatus,
  type TraceEdge,
  type TraceEvent,
  type TraceNode,
} from "./session";
import { setLiveBoundId, useSessionsStore } from "./sessions";
import { liveBoundId } from "./sessions";
import { useWorkforceStore } from "./workforce";
import type {
  PlanSubTask,
  SessionModeType,
  TaskInfo,
  WorkforceAgent,
} from "../types/workforce";

export interface LiveParkBundle {
  session: {
    messages: Message[];
    trace: TraceEvent[];
    traceNodes: TraceNode[];
    traceEdges: TraceEdge[];
    confirmQueue: ConfirmRequest[];
    settledConfirmIds: string[];
    autoApprovingConfirmIds: string[];
    currentStepId: string | null;
    pendingArtifacts: Array<FileArtifact & { call_id: string }>;
    memoryInjectedCount: number;
    runStatus: RunStatus;
    taskStartedAt: number | null;
    taskElapsedMs: number;
    budgetTokens: number;
    budgetMaxTokens: number;
    budgetSteps: number;
    alwaysAllowTools: string[];
  };
  workforce: {
    sessionMode: SessionModeType;
    taskAssigning: WorkforceAgent[];
    taskInfo: TaskInfo[];
    taskRunning: TaskInfo[];
    pendingPlan: { taskId: string; subtasks: PlanSubTask[] } | null;
  };
  preview: {
    open: boolean;
    tabs: SessionPreviewTab[];
    activeTabId: string | null;
    dirtyPaths: Record<string, boolean>;
  };
}

const parks = new Map<string, LiveParkBundle>();
const taskIdByProject = new Map<string, string>();

export function getProjectTaskId(projectId: string): string | undefined {
  return taskIdByProject.get(projectId);
}

export function rememberProjectTaskId(projectId: string, taskId: string): void {
  if (projectId && taskId) taskIdByProject.set(projectId, taskId);
}

export function dropProjectPark(projectId: string): void {
  parks.delete(projectId);
  taskIdByProject.delete(projectId);
}

export function captureLivePark(): LiveParkBundle {
  const s = useSessionStore.getState();
  const w = useWorkforceStore.getState();
  const p = usePreviewStore.getState();
  return {
    session: {
      messages: s.messages,
      trace: s.trace,
      traceNodes: s.traceNodes,
      traceEdges: s.traceEdges,
      confirmQueue: s.confirmQueue,
      settledConfirmIds: s.settledConfirmIds,
      autoApprovingConfirmIds: s.autoApprovingConfirmIds,
      currentStepId: s.currentStepId,
      pendingArtifacts: s.pendingArtifacts,
      memoryInjectedCount: s.memoryInjectedCount,
      runStatus: s.runStatus,
      taskStartedAt: s.taskStartedAt,
      taskElapsedMs: s.taskElapsedMs,
      budgetTokens: s.budgetTokens,
      budgetMaxTokens: s.budgetMaxTokens,
      budgetSteps: s.budgetSteps,
      alwaysAllowTools: s.alwaysAllowTools,
    },
    workforce: {
      sessionMode: w.sessionMode,
      taskAssigning: w.taskAssigning,
      taskInfo: w.taskInfo,
      taskRunning: w.taskRunning,
      pendingPlan: w.pendingPlan,
    },
    preview: {
      open: p.open,
      tabs: p.tabs,
      activeTabId: p.activeTabId,
      dirtyPaths: p.dirtyPaths,
    },
  };
}

export function loadLivePark(bundle: LiveParkBundle): void {
  useSessionStore.setState({ ...bundle.session });
  useWorkforceStore.setState({
    sessionMode: bundle.workforce.sessionMode,
    taskAssigning: bundle.workforce.taskAssigning,
    taskInfo: bundle.workforce.taskInfo,
    taskRunning: bundle.workforce.taskRunning,
    pendingPlan: bundle.workforce.pendingPlan,
  });
  usePreviewStore.setState({
    open: bundle.preview.open,
    tabs: bundle.preview.tabs,
    activeTabId: bundle.preview.activeTabId,
    dirtyPaths: bundle.preview.dirtyPaths,
  });
}

export function clearLiveToIdle(messages: Message[]): void {
  useSessionStore.getState().replaceMessages(messages);
  useSessionStore.getState().resetLiveState();
  useWorkforceStore.getState().reset();
  usePreviewStore.getState().reset();
}

export function parkProject(projectId: string): void {
  if (!projectId) return;
  const bundle = captureLivePark();
  parks.set(projectId, bundle);
  useSessionsStore.getState().saveMessages(projectId, bundle.session.messages);
}

export function restoreProject(
  projectId: string,
  fallbackMessages: Message[],
): void {
  const park = parks.get(projectId);
  if (park) {
    loadLivePark(park);
    return;
  }
  clearLiveToIdle(fallbackMessages);
}

function emptyParkFromMessages(messages: Message[]): LiveParkBundle {
  clearLiveToIdle(messages);
  return captureLivePark();
}

/** Run a sync mutation against a project's live UI (active store or parked). */
export function applyToProject(projectId: string, fn: () => void): void {
  if (!projectId || liveBoundId === projectId) {
    fn();
    return;
  }

  const prevBound = liveBoundId;
  const current = prevBound ? captureLivePark() : null;
  setLiveBoundId(null);

  try {
    const park =
      parks.get(projectId) ??
      emptyParkFromMessages(useSessionsStore.getState().getMessages(projectId));
    loadLivePark(park);
    fn();
    const updated = captureLivePark();
    parks.set(projectId, updated);
    useSessionsStore.getState().saveMessages(projectId, updated.session.messages);
  } finally {
    if (current) loadLivePark(current);
    setLiveBoundId(prevBound);
  }
}

export function dispatchProjectEvent(projectId: string, event: SSEvent): void {
  const tid = event.payload?.task_id;
  if (typeof tid === "string" && tid) {
    rememberProjectTaskId(projectId, tid);
  }

  applyToProject(projectId, () => {
    useSessionStore.getState().handleEvent(event, projectId);
  });

  if (event.type === "graph.start") {
    useSessionsStore.getState().touchSession(projectId, { status: "running" });
  }
  if (event.type === "graph.end") {
    useSessionsStore.getState().touchSession(projectId, {
      status: event.payload.status === "error" ? "error" : "done",
    });
  }
}
