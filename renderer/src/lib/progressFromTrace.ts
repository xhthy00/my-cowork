/**
 * Derive Eigent-like Progress / WorkLog rows from LangGraph SSE trace + workforce tasks.
 */
import type { TraceEvent } from "../store/session";
import type { TaskInfo } from "../types/workforce";
import {
  formatWorkLogLine,
  humanizeAgent,
  humanizeAssignContent,
  humanizeTool,
} from "./processLabels";

export type ProgressItem = {
  id: string;
  content: string;
  status: "waiting" | "running" | "completed" | "failed" | "blocked";
  substeps: Array<{ id: string; content: string; status: ProgressItem["status"] }>;
};

const NOISE_NODES = new Set(["__start__", "__end__", "start", "end"]);
const AGENT_STEP_NODES = new Set([
  "single_agent",
  "synthesize",
  "coordinator",
  "supervisor",
  "developer_agent",
  "browser_agent",
  "document_agent",
  "multi_modal_agent",
  "file_worker",
  "doc_worker",
  "web_worker",
  "msg_worker",
]);

const WORKER_NOISE =
  /^(Running|Finished)\s+(developer_agent|browser_agent|document_agent|multi_modal_agent|file_worker|doc_worker|web_worker|msg_worker|supervisor|coordinator|single_agent)\s*$/i;
const WORKER_NOISE_ZH =
  /^(正在运行|已完成)\s*[·•\-]\s*(developer_agent|browser_agent|document_agent|multi_modal_agent|file_worker|doc_worker|web_worker|msg_worker|supervisor|coordinator|single_agent)\s*$/i;

export { humanizeTool, humanizeAgent, humanizeAssignContent, formatWorkLogLine };

/** Prefer todo_state plan in taskInfo; never show raw worker assign noise. */
export function buildProgressItems(
  taskInfo: TaskInfo[],
): ProgressItem[] {
  const planned = taskInfo.filter((t) => {
    const c = t.content.trim();
    return c && !WORKER_NOISE.test(c) && !WORKER_NOISE_ZH.test(c);
  });
  return planned.map((t) => ({
      id: t.id,
      content: humanizeAssignContent(t.content, t.agent),
      status: t.status || "waiting",
      substeps: (t.substeps || []).map((child) => ({
        id: child.id,
        content: child.content,
        status: t.status === "completed" && (child.status === "waiting" || child.status === "running")
          ? "completed"
          : child.status || "waiting",
      })),
    }));
}

/** Tool calls are execution details, never plan steps or progress counters. */
export function buildStepExecutionDetails(
  trace: TraceEvent[],
  taskInfo: TaskInfo[],
): Record<string, Array<{ id: string; label: string; done: boolean }>> {
  const out: Record<string, Array<{ id: string; label: string; done: boolean }>> = {};
  const assignedByAgent = new Map<string, string>();
  let singleCurrent = "";
  for (const ev of trace) {
    if (ev.type === "todo_state" && Array.isArray(ev.payload.todos)) {
      const rows = ev.payload.todos as Array<Record<string, unknown>>;
      singleCurrent = String(rows.find((row) => row.status === "in_progress")?.id ?? singleCurrent);
      continue;
    }
    if (ev.type === "agent.assign" || ev.type === "assign_task") {
      const agent = String(ev.payload.agent_id ?? "");
      const id = String(ev.payload.sub_task_id ?? ev.payload.assign_id ?? "");
      if (agent && taskInfo.some((t) => t.id === id)) assignedByAgent.set(agent, id);
      continue;
    }
    if (ev.type !== "tool.start" && ev.type !== "tool.result") continue;
    const tool = String(ev.payload.tool ?? "");
    if (!tool || tool === "todo_write") continue;
    const agent = String(ev.payload.agent_id ?? "");
    const parentId = String(ev.payload.sub_task_id ?? "")
      || assignedByAgent.get(agent)
      || (agent === "single_agent" ? singleCurrent : undefined);
    if (!parentId) continue;
    const id = String(ev.payload.call_id ?? ev.payload.id ?? ev.id);
    const details = out[parentId] || (out[parentId] = []);
    const existing = details.find((d) => d.id === id);
    if (existing) {
      if (ev.type === "tool.result") existing.done = true;
    } else {
      details.push({ id, label: humanizeTool(tool), done: ev.type === "tool.result" });
    }
  }
  return out;
}

export type WorkLogStep = {
  id: string;
  label: string;
  detail?: string;
  preview?: string;
  kind: "prep" | "tool" | "file";
  status?: "running" | "done";
  agentId?: string;
  /** Original tool / node id for icons; not shown in the UI. */
  tool?: string;
};

export function findInFlightTool(trace: TraceEvent[]): {
  tool: string;
  preview: string;
  startedAtMs: number | null;
} | null {
  const done = new Set<string>();
  for (let i = trace.length - 1; i >= 0; i--) {
    const ev = trace[i];
    const callId = String(ev.payload.call_id ?? ev.payload.id ?? "");
    if (ev.type === "tool.result") {
      if (callId) done.add(callId);
      continue;
    }
    if (ev.type !== "tool.start" && ev.type !== "tool.confirm_request") continue;
    if (callId && done.has(callId)) continue;
    const tool = String(ev.payload.tool ?? "").trim();
    if (!tool) continue;
    const ts = Date.parse(String(ev.payload.timestamp ?? ""));
    return {
      tool,
      preview: String(ev.payload.preview ?? "").trim(),
      startedAtMs: Number.isFinite(ts) ? ts : null,
    };
  }
  return null;
}

/** Steps shown under "Worked for …" in the chat column. */
export function buildWorkLogSteps(
  trace: TraceEvent[],
  artifactNames: string[],
): WorkLogStep[] {
  const steps: WorkLogStep[] = [];
  let registered = 0;

  for (const ev of trace) {
    if (ev.type === "agent.create" || ev.type === "agent.activate") {
      registered += 1;
    }
  }
  if (registered > 0) {
    steps.push({
      id: "prep",
      label: `准备智能体 · 已注册 ${registered} 个`,
      kind: "prep",
    });
  }

  const toolIndex = new Map<string, number>();
  for (const ev of trace) {
    if (
      ev.type === "tool.start" ||
      ev.type === "tool.confirm_request" ||
      ev.type === "tool.result"
    ) {
      const tool = String(ev.payload.tool ?? "").trim();
      if (!tool) continue;
      const callId = String(ev.payload.call_id ?? ev.payload.id ?? "");
      const preview = String(ev.payload.preview ?? "").trim();
      const status = ev.type === "tool.result" ? "done" : "running";
      const key = callId || `name:${tool}`;
      const idx = toolIndex.get(key);
      if (idx != null) {
        const prev = steps[idx];
        steps[idx] = {
          ...prev,
          preview: preview || prev.preview,
          status,
          tool: tool || prev.tool,
        };
        continue;
      }
      if (!callId && ev.type === "tool.result" && toolIndex.has(`name:${tool}`)) {
        continue;
      }
      toolIndex.set(key, steps.length);
      steps.push({
        id: key,
        label: humanizeTool(tool),
        preview: preview || undefined,
        kind: "tool",
        status,
        agentId: String(ev.payload.agent_id ?? "") || undefined,
        tool,
      });
    } else if (ev.type === "graph.step") {
      const node = String(ev.payload.node ?? "");
      if (
        !node ||
        NOISE_NODES.has(node) ||
        AGENT_STEP_NODES.has(node)
      ) {
        continue;
      }
      const key = `node:${node}`;
      if (toolIndex.has(key)) continue;
      toolIndex.set(key, steps.length);
      steps.push({
        id: String(ev.payload.id ?? ev.id),
        label: humanizeAgent(node),
        kind: "tool",
        status: "done",
        agentId: node,
        tool: node,
      });
    }
  }

  // One row per unique file; show the real name (not a generic duplicate label).
  const seenFiles = new Set<string>();
  for (const name of artifactNames) {
    const key = name.trim();
    if (!key || seenFiles.has(key)) continue;
    seenFiles.add(key);
    steps.push({
      id: `file:${key}`,
      label: key,
      detail: key,
      kind: "file",
    });
  }

  return steps;
}

export type ContextItem = {
  id: string;
  label: string;
  category: "skill" | "connector" | "file";
};

export function buildContextItems(
  trace: TraceEvent[],
  artifactNames: string[],
): ContextItem[] {
  const items: ContextItem[] = [];
  const seen = new Set<string>();

  for (const ev of trace) {
    if (ev.type !== "tool.confirm_request" && ev.type !== "tool.result") continue;
    const tool = String(ev.payload.tool ?? "").trim();
    if (!tool) continue;
    const label = humanizeTool(tool);
    if (seen.has(label)) continue;
    seen.add(label);
    items.push({
      id: tool,
      label,
      category: /mcp|connector/i.test(tool) ? "connector" : "skill",
    });
  }

  for (const name of artifactNames) {
    const ext = name.includes(".") ? name.split(".").pop()! : name;
    if (seen.has(ext)) continue;
    seen.add(ext);
    items.push({ id: `skill:${ext}`, label: ext, category: "skill" });
  }

  return items;
}
