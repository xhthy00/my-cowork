/**
 * Adapted from eigent: src/types/constants.ts (SessionMode) + chatStore agent shapes.
 */
export const SessionMode = {
  WORKFORCE: "workforce",
  SINGLE_AGENT: "single-agent",
} as const;

export type SessionModeType = (typeof SessionMode)[keyof typeof SessionMode];

export type WorkerType =
  | "developer_agent"
  | "browser_agent"
  | "document_agent"
  | "multi_modal_agent"
  | "supervisor"
  | "coordinator"
  | "single_agent"
  // legacy
  | "file_worker"
  | "doc_worker"
  | "web_worker"
  | "msg_worker";

export type TaskStatus =
  | "waiting"
  | "running"
  | "completed"
  | "failed"
  | "blocked";

export interface TaskInfo {
  id: string;
  content: string;
  /** Eigent-style present continuous label while running */
  active_form?: string;
  status?: TaskStatus;
  agent?: string;
  terminal?: string[];
  /** Eigent AgentPool toolkit chips (optional). */
  toolkits?: {
    toolkitName: string;
    toolkitStatus?: string;
    toolkitId?: string;
    toolkitMethods?: string;
  }[];
}

export interface WorkforceAgent {
  agent_id: string;
  name: string;
  type: WorkerType;
  status?: "idle" | "running" | "done" | "error";
  tasks: TaskInfo[];
  log: string[];
  tools?: string[];
  /** Task completion progress (completed/total). */
  progress?: { completed: number; total: number };
}

export interface PlanSubTask {
  id: string;
  content: string;
  assignee: string;
  dependencies?: string[];
  status?: string;
}
