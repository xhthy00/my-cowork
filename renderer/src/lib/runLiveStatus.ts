/**
 * Live “the system is still working” copy for WorkLog + the composer strip.
 */
import type { TraceEvent } from "../store/session";
import type { TaskInfo } from "../types/workforce";
import { formatSplittingElapsed } from "./formatElapsed";
import {
  humanizeAgent,
  humanizeAssignContent,
  humanizeTool,
} from "./processLabels";
import { findInFlightTool } from "./progressFromTrace";

export type LiveActivity = {
  label: string;
  phase: string;
};

const QUIET_MS = 4000;

export function deriveLiveActivity(opts: {
  trace: TraceEvent[];
  taskInfo: TaskInfo[];
  taskRunning: TaskInfo[];
  confirmCount: number;
  pendingArtifactCount: number;
  thinkingSubject?: string | null;
  hasPrepStep?: boolean;
  /** Milliseconds since last model token / tool progress (heartbeats ignored). */
  quietMs?: number;
  /** True when the backend is still pinging during an in-flight LLM call. */
  beating?: boolean;
}): LiveActivity {
  const trace = Array.isArray(opts.trace) ? opts.trace : [];
  const taskInfo = Array.isArray(opts.taskInfo) ? opts.taskInfo : [];
  const taskRunning = Array.isArray(opts.taskRunning) ? opts.taskRunning : [];
  const inflight = findInFlightTool(trace);
  const thinking = (opts.thinkingSubject ?? "").trim();

  let label = "思考中…";
  if (opts.confirmCount > 0) {
    const lastConfirm = [...trace]
      .reverse()
      .find((ev) => ev.type === "tool.confirm_request");
    const tool = String(lastConfirm?.payload.tool ?? "工具");
    label = `等待确认 · ${humanizeTool(tool)}`;
  } else if (inflight) {
    const bits = [humanizeTool(inflight.tool)];
    if (inflight.preview) bits.push(inflight.preview);
    label = bits.join(" · ");
  } else if (thinking && thinking !== "开始分析任务") {
    label = thinking;
  } else {
    const runningTodo =
      taskInfo.find((t) => t.status === "running") ||
      taskRunning[0] ||
      taskInfo.find((t) => t.status === "waiting");
    if (runningTodo?.active_form?.trim()) {
      label = runningTodo.active_form.trim();
    } else if (runningTodo?.content?.trim()) {
      label = runningTodo.content.trim();
    } else {
      const lastAssign = [...trace]
        .reverse()
        .find((ev) => ev.type === "agent.assign");
      if (lastAssign) {
        const content = String(lastAssign.payload.content ?? "").trim();
        const agent = String(lastAssign.payload.agent_id ?? "");
        const localized = humanizeAssignContent(content, agent);
        if (localized && !/^正在运行|^已完成/i.test(localized)) {
          label = localized;
        } else if (agent) {
          label = `正在执行 · ${humanizeAgent(agent)}`;
        }
      } else if (opts.hasPrepStep) {
        label = "正在准备智能体…";
      } else if (thinking) {
        label = thinking;
      }
    }
  }

  let phase = "正在启动任务";
  if (opts.confirmCount > 0) phase = "等待你确认工具调用";
  else if (inflight) phase = "工具执行中";
  else if ((opts.quietMs ?? 0) >= QUIET_MS) {
    const quiet = formatSplittingElapsed(opts.quietMs ?? 0);
    phase = opts.beating
      ? `深度思考中 · 已静默 ${quiet}（连接正常）`
      : `深度思考中 · 已静默 ${quiet}`;
  } else if (/生成回答|撰写|正在写|正在组装|正在写入/.test(thinking)) {
    phase = "正在组织回答";
  } else if (opts.pendingArtifactCount > 0) phase = "文件已生成，任务收尾中";
  else if (trace.some((e) => e.type === "todo_state")) phase = "按计划执行中";
  else if (trace.some((e) => e.type === "graph.start")) phase = "已连接后端";

  return { label, phase };
}
