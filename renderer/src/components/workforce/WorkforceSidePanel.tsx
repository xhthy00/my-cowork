/**
 * Adapted from eigent: ProjectModeToggle + FoldedPanel / FoldedAgentCard.
 * Horizontal agent strip under chat header — avoids a permanent vertical column.
 *
 * Enhanced: WorkforcePanel — full workforce topology view with list/topology toggle.
 */
import { Users, X } from "lucide-react";
import { SessionMode, type SessionModeType } from "../../types/workforce";
import { useWorkforceStore } from "../../store/workforce";
import WorkforceTopologyView from "./WorkforceTopologyView";
import { Button } from "../ui/button";

export function SessionModeToggle() {
  const mode = useWorkforceStore((s) => s.sessionMode);
  const setMode = useWorkforceStore((s) => s.setSessionMode);

  return (
    <div className="mode-toggle" role="group" aria-label="会话模式">
      {(
        [
          [SessionMode.WORKFORCE, "多智能体"],
          [SessionMode.SINGLE_AGENT, "单智能体"],
        ] as [SessionModeType, string][]
      ).map(([id, label]) => (
        <button
          key={id}
          type="button"
          className={`mode-toggle-btn ${mode === id ? "active" : ""}`}
          onClick={() => setMode(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default function WorkforceAgentStrip() {
  const agents = useWorkforceStore((s) => s.taskAssigning);
  const taskRunning = useWorkforceStore((s) => s.taskRunning);
  const mode = useWorkforceStore((s) => s.sessionMode);

  if (mode !== SessionMode.WORKFORCE) return null;

  return (
    <div className="agent-strip" aria-label="智能体池">
      <div className="agent-strip-meta">
        <span className="agent-strip-label">智能体</span>
        <span className="agent-strip-running">
          {taskRunning.length > 0 ? `${taskRunning.length} 运行中` : "空闲"}
        </span>
      </div>
      <div className="agent-strip-list">
        {agents.map((agent) => {
          const latest = agent.tasks[agent.tasks.length - 1];
          return (
            <div
              key={agent.agent_id}
              className={`agent-chip status-${agent.status || "idle"}`}
              title={latest?.content || agent.type}
            >
              <span className={`agent-chip-dot ${agent.status || "idle"}`} />
              <span className="agent-chip-name">{agent.name}</span>
              {latest && agent.status === "running" && (
                <span className="agent-chip-task">{latest.content.slice(0, 24)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Enhanced workforce panel — full topology view with list/topology toggle. */
export function WorkforcePanel({
  onClose,
}: {
  onClose?: () => void;
}) {
  const mode = useWorkforceStore((s) => s.sessionMode);

  if (mode !== SessionMode.WORKFORCE) return null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-ds-border-neutral-subtle-default px-3 py-2">
        <div className="flex items-center gap-1.5 text-[14px] font-semibold text-ds-text-neutral-default-default">
          <Users className="h-4 w-4 text-ds-text-neutral-muted-default" />
          智能体团队
        </div>
        {onClose && (
          <Button size="icon" variant="ghost" title="关闭" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
      <div className="flex-1 min-h-0 p-2">
        <WorkforceTopologyView />
      </div>
    </div>
  );
}
