/**
 * Adapted from eigent: src/store/chatStore.ts (taskAssigning / sessionMode fields).
 */
import { create } from "zustand";

import {
  SessionMode,
  type PlanSubTask,
  type SessionModeType,
  type TaskInfo,
  type TaskStatus,
  type WorkforceAgent,
  type WorkerType,
} from "../types/workforce";

interface WorkforceState {
  sessionMode: SessionModeType;
  taskAssigning: WorkforceAgent[];
  taskInfo: TaskInfo[];
  taskRunning: TaskInfo[];
  /** Pending plan awaiting user confirm (Eigent PlanTaskBox). */
  pendingPlan: { taskId: string; subtasks: PlanSubTask[] } | NonePlan;
  setSessionMode: (mode: SessionModeType) => void;
  reset: () => void;
  seedPlan: (tasks: TaskInfo[]) => void;
  clearPendingPlan: () => void;
  upsertAgent: (agent: Partial<WorkforceAgent> & { agent_id: string; type: WorkerType }) => void;
  removeAgent: (agentId: string) => void;
  duplicateAgent: (agentId: string) => void;
  setAgentStatus: (agentId: string, status: WorkforceAgent["status"]) => void;
  assignTask: (agentId: string, task: TaskInfo) => void;
  updateTaskStatus: (taskId: string, status: TaskStatus) => void;
  appendTerminal: (agentId: string, taskId: string, output: string) => void;
  handleWorkforceEvent: (type: string, payload: Record<string, unknown>) => void;
}

type NonePlan = null;

const BASE_AGENTS: WorkforceAgent[] = [
  {
    agent_id: "developer_agent",
    name: "Developer Agent",
    type: "developer_agent",
    status: "idle",
    tasks: [],
    log: [],
  },
  {
    agent_id: "browser_agent",
    name: "Browser Agent",
    type: "browser_agent",
    status: "idle",
    tasks: [],
    log: [],
  },
  {
    agent_id: "document_agent",
    name: "Document Agent",
    type: "document_agent",
    status: "idle",
    tasks: [],
    log: [],
  },
  {
    agent_id: "multi_modal_agent",
    name: "Multi Modal Agent",
    type: "multi_modal_agent",
    status: "idle",
    tasks: [],
    log: [],
  },
];

export const BASE_WORKFORCE_AGENT_IDS = new Set(
  BASE_AGENTS.map((a) => a.agent_id),
);

export function isBaseWorkforceAgent(agentId: string): boolean {
  return BASE_WORKFORCE_AGENT_IDS.has(agentId);
}

export const useWorkforceStore = create<WorkforceState>((set, get) => ({
  sessionMode: SessionMode.SINGLE_AGENT,
  taskAssigning: BASE_AGENTS.map((a) => ({ ...a, tasks: [] })),
  taskInfo: [],
  taskRunning: [],
  pendingPlan: null,

  setSessionMode: (mode) => set({ sessionMode: mode }),

  reset: () =>
    set({
      taskAssigning: BASE_AGENTS.map((a) => ({ ...a, tasks: [], status: "idle", log: [] })),
      taskInfo: [],
      taskRunning: [],
      pendingPlan: null,
    }),

  seedPlan: (tasks) =>
    set({
      taskInfo: tasks,
      taskRunning: tasks.filter((t) => t.status === "running"),
    }),

  clearPendingPlan: () => set({ pendingPlan: null }),

  upsertAgent: (agent) =>
    set((state) => {
      const list = state.taskAssigning.slice();
      const idx = list.findIndex((a) => a.agent_id === agent.agent_id);
      if (idx >= 0) {
        list[idx] = { ...list[idx], ...agent, tasks: list[idx].tasks };
      } else {
        list.push({
          agent_id: agent.agent_id,
          name: agent.name || agent.agent_id,
          type: agent.type,
          status: agent.status || "idle",
          tasks: [],
          log: [],
          tools: agent.tools,
        });
      }
      return { taskAssigning: list };
    }),

  removeAgent: (agentId) => {
    if (isBaseWorkforceAgent(agentId)) return;
    set((state) => ({
      taskAssigning: state.taskAssigning.filter((a) => a.agent_id !== agentId),
    }));
  },

  duplicateAgent: (agentId) => {
    const src = get().taskAssigning.find((a) => a.agent_id === agentId);
    if (!src || isBaseWorkforceAgent(agentId)) return;
    const taken = new Set(get().taskAssigning.map((a) => a.agent_id));
    let newName = `${src.name} copy`;
    let n = 2;
    while (taken.has(newName)) {
      newName = `${src.name} copy ${n++}`;
    }
    get().upsertAgent({
      agent_id: newName,
      name: newName,
      type: src.type,
      status: "idle",
      tools: src.tools ? [...src.tools] : undefined,
    });
  },

  setAgentStatus: (agentId, status) =>
    set((state) => ({
      taskAssigning: state.taskAssigning.map((a) =>
        a.agent_id === agentId ? { ...a, status } : a,
      ),
    })),

  assignTask: (agentId, task) =>
    set((state) => {
      const hasPlan = state.taskInfo.some((t) => t.id.startsWith("todo_") || t.id.startsWith("task_"));
      const taskRunning = hasPlan
        ? state.taskRunning
        : task.status === "running"
          ? [...state.taskRunning.filter((t) => t.id !== task.id), task]
          : state.taskRunning.filter((t) => t.id !== task.id);
      return {
        taskInfo: hasPlan
          ? state.taskInfo
          : [...state.taskInfo.filter((t) => t.id !== task.id), task],
        taskRunning,
        taskAssigning: state.taskAssigning.map((a) => {
          if (a.agent_id !== agentId) return a;
          const prev = a.tasks.find((t) => t.id === task.id);
          const merged: TaskInfo = {
            ...prev,
            ...task,
            terminal:
              task.terminal && task.terminal.length > 0
                ? task.terminal
                : prev?.terminal || task.terminal || [],
          };
          const tasks = [...a.tasks.filter((t) => t.id !== task.id), merged];
          return {
            ...a,
            tasks,
            status: merged.status === "running" ? "running" : a.status,
          };
        }),
      };
    }),

  updateTaskStatus: (taskId, status) =>
    set((state) => {
      const patch = (t: TaskInfo) => (t.id === taskId ? { ...t, status } : t);
      const taskAssigning = state.taskAssigning.map((a) => {
        const tasks = a.tasks.map(patch);
        const completed = tasks.filter((t) => t.status === "completed" || t.status === "failed").length;
        return {
          ...a,
          tasks,
          progress: tasks.length > 0 ? { completed, total: tasks.length } : a.progress,
          status:
            status === "completed" || status === "failed"
              ? tasks.every(
                  (t) =>
                    t.id === taskId || t.status === "completed" || t.status === "failed",
                )
                ? status === "failed"
                  ? "error"
                  : "done"
                : a.status
              : a.status,
        };
      });
      return {
        taskInfo: state.taskInfo.map(patch),
        taskRunning:
          status === "running"
            ? state.taskRunning.map(patch)
            : state.taskRunning.filter((t) => t.id !== taskId),
        taskAssigning,
      };
    }),

  appendTerminal: (agentId, taskId, output) =>
    set((state) => ({
      taskAssigning: state.taskAssigning.map((a) => {
        if (a.agent_id !== agentId) return a;
        const exact = taskId
          ? a.tasks.find((t) => t.id === taskId)
          : undefined;
        const target =
          exact ||
          a.tasks.find((t) => t.status === "running") ||
          a.tasks[a.tasks.length - 1];
        if (target) {
          return {
            ...a,
            tasks: a.tasks.map((t) =>
              t.id === target.id
                ? { ...t, terminal: [...(t.terminal || []), output] }
                : t,
            ),
          };
        }
        return {
          ...a,
          tasks: [
            {
              id: taskId || `term-${Date.now()}`,
              content: "终端输出",
              status: "running" as TaskStatus,
              agent: agentId,
              terminal: [output],
            },
          ],
        };
      }),
    })),

  handleWorkforceEvent: (type, payload) => {
    const s = get();
    if (type === "to_sub_tasks") {
      const raw = Array.isArray(payload.subtasks) ? payload.subtasks : [];
      const subtasks: PlanSubTask[] = raw.map((row, index) => {
        const item = row as Record<string, unknown>;
        return {
          id: String(item.id ?? `task_${index + 1}`),
          content: String(item.content ?? ""),
          assignee: String(item.assignee ?? "browser_agent"),
          dependencies: Array.isArray(item.dependencies)
            ? item.dependencies.map(String)
            : [],
          status: String(item.status ?? "waiting"),
        };
      });
      // Eigent: Progress = confirmed/pending sub_tasks (not worker todo_write).
      const taskInfo: TaskInfo[] = subtasks
        .filter((t) => t.content.trim())
        .map((t) => ({
          id: t.id,
          content: t.content,
          status: "waiting" as TaskStatus,
          agent: t.assignee,
          terminal: [],
        }));
      set({
        sessionMode: SessionMode.WORKFORCE,
        pendingPlan: {
          taskId: String(payload.task_id ?? ""),
          subtasks,
        },
        taskInfo,
        taskRunning: [],
      });
      return;
    }
    if (type === "todo_state") {
      const raw = Array.isArray(payload.todos) ? payload.todos : [];
      const mapStatus = (statusRaw: string): TaskStatus =>
        statusRaw === "completed"
          ? "completed"
          : statusRaw === "in_progress"
            ? "running"
            : statusRaw === "failed"
              ? "failed"
              : "waiting";

      const existing = s.taskInfo;
      const workforcePlan =
        s.sessionMode === SessionMode.WORKFORCE &&
        existing.some((t) => t.id.startsWith("task_"));

      if (workforcePlan) {
        // Keep confirmed plan wording; only sync status by id (Eigent Progress).
        const incoming = new Map<string, Record<string, unknown>>();
        for (const todo of raw) {
          const row = todo as Record<string, unknown>;
          const id = String(row.id ?? "");
          if (id) incoming.set(id, row);
        }
        const overlap = existing.filter((t) => incoming.has(t.id)).length;
        if (overlap === 0) {
          // Foreign rewrite (e.g. legacy worker todo_write) — ignore.
          return;
        }
        const taskInfo = existing.map((t) => {
          const row = incoming.get(t.id);
          if (!row) return t;
          return {
            ...t,
            status: mapStatus(String(row.status ?? "pending")),
            agent: String(row.agent ?? t.agent ?? payload.agent_id ?? ""),
          };
        });
        set({
          taskInfo,
          taskRunning: taskInfo.filter((t) => t.status === "running"),
        });
        return;
      }

      // Single-agent: Eigent replaces Progress from todo_write.
      const taskInfo: TaskInfo[] = raw.map((todo, index) => {
        const row = todo as Record<string, unknown>;
        const status = mapStatus(String(row.status ?? "pending"));
        const content = String(row.content ?? "");
        const active_form =
          row.active_form != null && String(row.active_form).trim()
            ? String(row.active_form)
            : undefined;
        return {
          id: String(row.id ?? `todo_${index + 1}`),
          content: status === "running" && active_form ? active_form : content,
          active_form,
          status,
          agent: String(row.agent ?? payload.agent_id ?? "single_agent"),
          terminal: [],
        };
      });
      set({
        sessionMode: SessionMode.SINGLE_AGENT,
        taskInfo,
        taskRunning: taskInfo.filter((t) => t.status === "running"),
        taskAssigning: s.taskAssigning.map((a) =>
          a.agent_id === "single_agent" || a.type === "supervisor"
            ? a
            : {
                ...a,
                tasks:
                  a.status === "running"
                    ? taskInfo.filter((t) => t.status === "running" || t.status === "waiting")
                    : a.tasks,
              },
        ),
      });
      return;
    }
    if (type === "agent.create") {
      s.upsertAgent({
        agent_id: String(payload.agent_id ?? payload.agent_type ?? payload.type ?? "worker"),
        name: String(payload.name ?? payload.agent_id ?? "Worker"),
        type:
          (payload.agent_type as WorkerType) ||
          (payload.type as WorkerType) ||
          "developer_agent",
        status: "idle",
      });
    } else if (type === "agent.activate") {
      s.setAgentStatus(String(payload.agent_id), "running");
    } else if (type === "agent.deactivate") {
      const id = String(payload.agent_id);
      const agent = get().taskAssigning.find((a) => a.agent_id === id);
      s.setAgentStatus(id, agent?.status === "error" ? "error" : "done");
    } else if (type === "agent.assign" || type === "assign_task") {
      s.assignTask(String(payload.agent_id), {
        id: String(payload.assign_id ?? payload.sub_task_id ?? `t-${Date.now()}`),
        content: String(payload.content ?? ""),
        status: (payload.status as TaskStatus) || "running",
        agent: String(payload.agent_id),
        terminal: [],
      });
    } else if (type === "task_state") {
      s.updateTaskStatus(
        String(payload.sub_task_id ?? ""),
        (payload.status as TaskStatus) || "completed",
      );
    } else if (type === "agent.terminal") {
      s.appendTerminal(
        String(payload.agent_id),
        String(payload.assign_id ?? payload.sub_task_id ?? ""),
        String(payload.output ?? ""),
      );
    }
  },
}));
