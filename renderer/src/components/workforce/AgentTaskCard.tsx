/**
 * Agent task card — shows one agent's status, tasks, and progress.
 * Adapted from eigent WorkFlow node + AionUi agent components.
 */
import { CheckCircle2, ChevronDown, ChevronUp, Circle, Loader2, XCircle } from "lucide-react";
import { useState } from "react";

import type { WorkforceAgent } from "../../types/workforce";
import type { TaskStatus } from "../../types/workforce";
import { cn } from "@/lib/utils";

const STATUS_CONFIG: Record<string, { dot: string; icon: typeof Circle; label: string }> = {
  idle: { dot: "bg-ds-text-neutral-subtle-default", icon: Circle, label: "空闲" },
  running: { dot: "bg-[var(--colors-green-default)] animate-pulse", icon: Loader2, label: "运行中" },
  done: { dot: "bg-ds-icon-status-completed-default", icon: CheckCircle2, label: "已完成" },
  error: { dot: "bg-[var(--danger)]", icon: XCircle, label: "出错" },
};

const TASK_STATUS_ICON: Record<TaskStatus, typeof Circle> = {
  waiting: Circle,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  blocked: Circle,
};

const TASK_STATUS_COLOR: Record<TaskStatus, string> = {
  waiting: "text-ds-text-neutral-subtle-default",
  running: "text-[var(--colors-green-default)]",
  completed: "text-ds-icon-status-completed-default",
  failed: "text-[var(--danger)]",
  blocked: "text-[var(--warning, #ff7d00)]",
};

export default function AgentTaskCard({
  agent,
  defaultExpanded,
}: {
  agent: WorkforceAgent;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);
  const cfg = STATUS_CONFIG[agent.status ?? "idle"] ?? STATUS_CONFIG.idle;
  const StatusIcon = cfg.icon;
  const hasTasks = agent.tasks.length > 0;
  const progress = agent.progress;

  return (
    <div
      className={cn(
        "rounded-xl border border-solid p-2.5 transition-colors",
        agent.status === "running"
          ? "border-[var(--colors-green-default)]/30 bg-[var(--colors-green-default)]/[0.03]"
          : "border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default",
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className={cn("h-2 w-2 shrink-0 rounded-full", cfg.dot)} />
        <StatusIcon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            cfg.label === "运行中" ? "animate-spin" : "",
            TASK_STATUS_COLOR[agent.status === "running" ? "running" : agent.status === "error" ? "failed" : agent.status === "done" ? "completed" : "waiting"],
          )}
        />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ds-text-neutral-default-default">
          {agent.name}
        </span>
        {progress && progress.total > 0 && (
          <span className="shrink-0 text-[11px] tabular-nums text-ds-text-neutral-subtle-default">
            {progress.completed}/{progress.total}
          </span>
        )}
        {hasTasks && (
          <button
            type="button"
            className="shrink-0 cursor-pointer rounded p-0.5 hover:bg-ds-bg-neutral-strong-default"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? (
              <ChevronUp className="h-3.5 w-3.5 text-ds-text-neutral-muted-default" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 text-ds-text-neutral-muted-default" />
            )}
          </button>
        )}
      </div>

      {/* Progress bar */}
      {progress && progress.total > 0 && (
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-ds-bg-neutral-strong-default">
          <div
            className="h-full rounded-full bg-[var(--colors-green-default)] transition-all duration-300"
            style={{ width: `${(progress.completed / progress.total) * 100}%` }}
          />
        </div>
      )}

      {/* Task list (expanded) */}
      {expanded && hasTasks && (
        <div className="mt-2 flex flex-col gap-1 border-t border-ds-border-neutral-subtle-default pt-2">
          {agent.tasks.map((task) => {
            const TaskIcon = TASK_STATUS_ICON[task.status ?? "waiting"] ?? Circle;
            return (
              <div key={task.id} className="flex items-start gap-1.5">
                <TaskIcon
                  className={cn(
                    "mt-0.5 h-3 w-3 shrink-0",
                    task.status === "running" && "animate-spin",
                    TASK_STATUS_COLOR[task.status ?? "waiting"],
                  )}
                />
                <span className="min-w-0 flex-1 text-[12px] leading-4 text-ds-text-neutral-default-default">
                  {task.content || task.id}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
