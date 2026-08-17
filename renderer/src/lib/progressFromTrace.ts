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
  status: "waiting" | "running" | "completed" | "failed";
};

const NOISE_NODES = new Set(["__start__", "__end__", "start", "end"]);

const WORKER_NOISE =
  /^(Running|Finished)\s+(developer_agent|browser_agent|document_agent|multi_modal_agent|file_worker|doc_worker|web_worker|msg_worker|supervisor|coordinator|single_agent)\s*$/i;
const WORKER_NOISE_ZH =
  /^(正在运行|已完成)\s*[·•\-]\s*(developer_agent|browser_agent|document_agent|multi_modal_agent|file_worker|doc_worker|web_worker|msg_worker|supervisor|coordinator|single_agent)\s*$/i;

export { humanizeTool, humanizeAgent, humanizeAssignContent, formatWorkLogLine };

/** Prefer todo_state plan in taskInfo; never show raw worker assign noise. */
export function buildProgressItems(
  taskInfo: TaskInfo[],
  trace: TraceEvent[],
  runDone: boolean,
): ProgressItem[] {
  const planned = taskInfo.filter((t) => {
    const c = t.content.trim();
    return c && !WORKER_NOISE.test(c) && !WORKER_NOISE_ZH.test(c);
  });
  if (planned.length > 0) {
    return planned.map((t) => ({
      id: t.id,
      content: humanizeAssignContent(t.content, t.assignee),
      status: (t.status === "completed" || runDone
        ? "completed"
        : t.status === "failed"
          ? "failed"
          : t.status === "running"
            ? "running"
            : "waiting") as ProgressItem["status"],
    }));
  }

  const items: ProgressItem[] = [];
  const seen = new Set<string>();

  for (const ev of trace) {
    if (ev.type === "agent.assign") {
      const raw = String(ev.payload.content ?? "").trim();
      const agent = String(ev.payload.agent_id ?? "");
      if (!raw) continue;
      const content = humanizeAssignContent(raw, agent);
      const id = String(ev.payload.assign_id ?? ev.payload.sub_task_id ?? ev.id);
      if (seen.has(id) || seen.has(content)) continue;
      seen.add(id);
      seen.add(content);
      items.push({
        id,
        content,
        status: runDone ? "completed" : "running",
      });
    } else if (ev.type === "graph.step" || ev.type === "step.start") {
      const node = String(ev.payload.node ?? "").trim();
      if (!node || NOISE_NODES.has(node) || node === "supervisor") continue;
      const label = humanizeAgent(node);
      if (seen.has(label)) continue;
      seen.add(label);
      items.push({
        id: String(ev.payload.id ?? ev.id),
        content: label,
        status: runDone ? "completed" : "running",
      });
    } else if (ev.type === "tool.confirm_request" || ev.type === "tool.result") {
      const tool = String(ev.payload.tool ?? "").trim();
      if (!tool) continue;
      const label = humanizeTool(tool);
      if (seen.has(label)) continue;
      seen.add(label);
      items.push({
        id: String(ev.payload.call_id ?? ev.payload.id ?? ev.id),
        content: label,
        status: runDone ? "completed" : "running",
      });
    }
  }

  // Mark all but last as completed while running (Eigent todo progression feel)
  if (!runDone && items.length > 1) {
    return items.map((it, i) =>
      i < items.length - 1 ? { ...it, status: "completed" as const } : it,
    );
  }
  return items;
}

export type WorkLogStep = {
  id: string;
  label: string;
  detail?: string;
  kind: "prep" | "tool" | "file";
};

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

  const seenTools = new Set<string>();
  const seenAssign = new Set<string>();
  for (const ev of trace) {
    if (ev.type === "agent.assign") {
      const content = String(ev.payload.content ?? "").trim();
      const agent = String(ev.payload.agent_id ?? "agent");
      if (!content) continue;
      const localized = humanizeAssignContent(content, agent);
      // Same plan line assigned to multiple workers → one WorkLog row.
      const dedupeKey = localized.toLowerCase();
      if (seenAssign.has(dedupeKey)) continue;
      seenAssign.add(dedupeKey);
      steps.push({
        id: String(ev.payload.assign_id ?? ev.payload.sub_task_id ?? ev.id),
        label: localized,
        detail: agent,
        kind: "tool",
      });
    } else if (ev.type === "tool.confirm_request" || ev.type === "tool.result") {
      const tool = String(ev.payload.tool ?? "").trim();
      if (!tool || seenTools.has(tool)) continue;
      seenTools.add(tool);
      steps.push({
        id: String(ev.payload.call_id ?? ev.payload.id ?? ev.id),
        label: humanizeTool(tool),
        kind: "tool",
      });
    } else if (ev.type === "graph.step") {
      const node = String(ev.payload.node ?? "");
      if (!node || NOISE_NODES.has(node) || node === "supervisor") continue;
      const key = `node:${node}`;
      if (seenTools.has(key)) continue;
      seenTools.add(key);
      steps.push({
        id: String(ev.payload.id ?? ev.id),
        label: humanizeAgent(node),
        kind: "tool",
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
