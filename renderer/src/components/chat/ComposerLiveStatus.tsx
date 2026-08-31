/**
 * Sticky live status above the composer — always visible while a run is
 * in progress so the user can see the system is still working.
 */
import { useEffect, useMemo, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";

import { orbStateFromSubject } from "@/components/chat/ThoughtDisplay";
import ShinyText from "@/components/ui/ShinyText";
import { formatSplittingElapsed } from "@/lib/formatElapsed";
import { formatTokenCount } from "@/lib/formatTokens";
import { deriveLiveActivity } from "@/lib/runLiveStatus";
import { useSessionStore } from "@/store/session";
import { useWorkforceStore } from "@/store/workforce";

export default function ComposerLiveStatus() {
  const runStatus = useSessionStore((s) => s.runStatus);
  const taskStartedAt = useSessionStore((s) => s.taskStartedAt);
  const taskElapsedMs = useSessionStore((s) => s.taskElapsedMs);
  const budgetTokens = useSessionStore((s) => s.budgetTokens);
  const budgetMaxTokens = useSessionStore((s) => s.budgetMaxTokens);
  const confirmQueue = useSessionStore((s) => s.confirmQueue) ?? [];
  const trace = useSessionStore((s) => s.trace) ?? [];
  const pendingArtifacts = useSessionStore((s) => s.pendingArtifacts) ?? [];
  const thinking = useSessionStore((s) => s.thinking);
  const lastContentAt = useSessionStore((s) => s.lastContentAt);
  const lastBeatAt = useSessionStore((s) => s.lastBeatAt);
  const taskInfo = useWorkforceStore((s) => s.taskInfo) ?? [];
  const taskRunning = useWorkforceStore((s) => s.taskRunning) ?? [];
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (runStatus !== "running" || !taskStartedAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [runStatus, taskStartedAt]);

  const quietMs = lastContentAt
    ? Math.max(0, now - lastContentAt)
    : taskStartedAt
      ? Math.max(0, now - taskStartedAt)
      : 0;
  const beating = lastBeatAt != null && now - lastBeatAt < 5000;

  const activity = useMemo(
    () =>
      deriveLiveActivity({
        trace,
        taskInfo,
        taskRunning,
        confirmCount: confirmQueue.length,
        pendingArtifactCount: pendingArtifacts.length,
        thinkingSubject: thinking?.subject,
        hasPrepStep: trace.some(
          (e) => e.type === "agent.create" || e.type === "agent.activate",
        ),
        quietMs,
        beating,
      }),
    [
      trace,
      taskInfo,
      taskRunning,
      confirmQueue.length,
      pendingArtifacts.length,
      thinking?.subject,
      quietMs,
      beating,
    ],
  );

  if (runStatus !== "running") return null;

  const elapsedMs = taskStartedAt
    ? now - taskStartedAt + taskElapsedMs
    : taskElapsedMs;
  const timeLabel = formatSplittingElapsed(elapsedMs);
  const tokenLabel = `${formatTokenCount(budgetTokens)} tokens`;
  const tokenTitle =
    budgetMaxTokens > 0
      ? `本轮累计约 ${formatTokenCount(budgetTokens)} / ${formatTokenCount(budgetMaxTokens)} tokens（估算）`
      : "本轮累计 tokens（估算）";

  return (
    <div
      className="mb-1.5 flex w-full min-w-0 items-center gap-2 px-1 py-0.5"
      role="status"
      aria-live="polite"
      aria-label={`${activity.label}，已工作 ${timeLabel}，${tokenLabel}`}
    >
      <ThinkingOrb
        state={orbStateFromSubject(activity.label)}
        size={20}
        theme="auto"
        aria-label={activity.label}
        className="shrink-0"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-0">
        <ShinyText
          text={activity.label}
          speed={2.2}
          className="max-w-full truncate text-body-sm"
        />
        <span className="truncate text-[11px] text-ds-text-neutral-subtle-default">
          {activity.phase}
        </span>
      </div>
      <div
        className="shrink-0 text-right text-[11px] tabular-nums leading-tight text-ds-text-neutral-muted-default"
        title={tokenTitle}
      >
        <div>已工作 {timeLabel}</div>
        <div className="text-ds-text-neutral-subtle-default">{tokenLabel}</div>
      </div>
    </div>
  );
}
