/**
 * Client-side Progress seed while waiting for Eigent-style todo_state.
 * Does NOT invent domain-specific steps — backend LLM planner owns the split.
 */
import type { TaskInfo } from "../types/workforce";

/** Single placeholder until SSE `todo_state` arrives (Eigent todo_write). */
export function planTodosFromQuery(text: string): TaskInfo[] {
  const q = text.trim();
  if (!q) return [];
  const zh = /[\u4e00-\u9fff]/.test(q);
  return [
    {
      id: "todo_planning",
      content: "规划任务步骤",
      active_form: "正在规划任务步骤",
      status: "running",
      agent: "single_agent",
      terminal: [],
    },
  ];
}
