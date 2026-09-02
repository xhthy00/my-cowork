/**
 * Adapted from eigent: ChatBox/MessageItem/TaskWorkLogAccordion.tsx
 * Live wait UX: ShinyText header, active_form, Thinking…, animated steps.
 */
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  ChevronRight,
  Code2,
  FileSpreadsheet,
  FileText,
  Globe,
  ListChecks,
  MousePointerClick,
  StickyNote,
  Terminal,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";

import { ThinkBlock } from "@/components/chat/MessageContent";
import { orbStateFromSubject } from "@/components/chat/ThoughtDisplay";
import { collectStepThinks, assignThinksToSteps } from "@/lib/stepThinks";

import FileTypeIcon from "@/components/files/FileTypeIcon";
import ShinyText from "@/components/ui/ShinyText";
import { formatSplittingElapsed } from "@/lib/formatElapsed";
import { formatTokenCount } from "@/lib/formatTokens";
import { formatWorkLogLine } from "@/lib/processLabels";
import { buildWorkLogSteps, findInFlightTool, type WorkLogStep } from "@/lib/progressFromTrace";
import { deriveLiveActivity } from "@/lib/runLiveStatus";
import { cn } from "@/lib/utils";
import { usePageTabStore } from "@/store/pageTab";
import { usePreviewStore } from "@/store/preview";
import { useSessionStore } from "@/store/session";
import { useWorkforceStore } from "@/store/workforce";

function toolGlyph(tool?: string): LucideIcon {
  const key = (tool ?? "").toLowerCase();
  if (/search|web_fetch|http/.test(key)) return Globe;
  if (/browser/.test(key)) return MousePointerClick;
  if (/bash|exec/.test(key)) return Terminal;
  if (/\bhtml\b|code/.test(key)) return Code2;
  if (/todo/.test(key)) return ListChecks;
  if (/xlsx|csv|sheet/.test(key)) return FileSpreadsheet;
  if (/note/.test(key)) return StickyNote;
  if (/pptx|docx|pdf|fs[._\s]|write|read|list|mkdir/.test(key)) return FileText;
  return Wrench;
}

function ToolStepCard({
  step,
  isRunning,
  thinks,
  running,
}: {
  step: WorkLogStep;
  isRunning: boolean;
  thinks: { id: string; text: string; closed: boolean }[];
  running: boolean;
}) {
  const Icon = toolGlyph(step.tool);
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex min-w-0 flex-col gap-0.5"
    >
      <div
        className={cn(
          "flex min-w-0 items-start gap-2 rounded-lg border px-2.5 py-1.5",
          isRunning
            ? "border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default"
            : "border-transparent bg-ds-bg-neutral-muted-default/60 opacity-70",
        )}
      >
        <Icon
          size={14}
          strokeWidth={2}
          aria-hidden
          className="mt-0.5 shrink-0 text-ds-icon-neutral-muted-default"
        />
        <div className="min-w-0 flex-1">
          <div
            className={cn(
              "truncate text-body-sm",
              isRunning
                ? "font-medium text-ds-text-neutral-default-default"
                : "text-ds-text-neutral-subtle-default",
            )}
          >
            {isRunning ? (
              <ShinyText text={step.label} speed={2.6} className="truncate text-body-sm" />
            ) : (
              step.label
            )}
          </div>
          {step.preview ? (
            <div className="truncate text-[11px] text-ds-text-neutral-subtle-default">
              {step.preview}
            </div>
          ) : null}
        </div>
      </div>
      <StepThinkList thinks={thinks} running={running} />
    </motion.div>
  );
}

function StepThinkList({
  thinks,
  running,
}: {
  thinks: { id: string; text: string; closed: boolean }[];
  running: boolean;
}) {
  if (!thinks.length) return null;
  return (
    <div className="flex min-w-0 flex-col gap-1 py-0.5 pl-3">
      {thinks.map((t) => (
        <ThinkBlock
          key={t.id}
          think={{
            type: "think",
            text: t.text,
            closed: t.closed || !running,
          }}
        />
      ))}
    </div>
  );
}

export default function WorkLogAccordion({ className }: { className?: string }) {
  const runStatus = useSessionStore((s) => s.runStatus);
  const taskStartedAt = useSessionStore((s) => s.taskStartedAt);
  const taskElapsedMs = useSessionStore((s) => s.taskElapsedMs);
  const budgetTokens = useSessionStore((s) => s.budgetTokens);
  const budgetMaxTokens = useSessionStore((s) => s.budgetMaxTokens);
  const confirmQueue = useSessionStore((s) => s.confirmQueue);
  const trace = useSessionStore((s) => s.trace);
  const messages = useSessionStore((s) => s.messages);
  const pendingArtifacts = useSessionStore((s) => s.pendingArtifacts);
  const thinking = useSessionStore((s) => s.thinking);
  const lastContentAt = useSessionStore((s) => s.lastContentAt);
  const lastBeatAt = useSessionStore((s) => s.lastBeatAt);
  const taskInfo = useWorkforceStore((s) => s.taskInfo);
  const taskRunning = useWorkforceStore((s) => s.taskRunning);
  const [now, setNow] = useState(() => Date.now());
  const [outerOpen, setOuterOpen] = useState(() => runStatus === "running");

  useEffect(() => {
    if (runStatus !== "running" || !taskStartedAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [runStatus, taskStartedAt]);

  useEffect(() => {
    if (runStatus === "done" || runStatus === "error") setOuterOpen(false);
    else if (runStatus === "running") setOuterOpen(true);
  }, [runStatus]);

  const elapsedMs = useMemo(() => {
    if (runStatus === "running" && taskStartedAt) {
      return Date.now() - taskStartedAt + taskElapsedMs;
    }
    return taskElapsedMs;
  }, [runStatus, taskStartedAt, taskElapsedMs, now]);

  /** Only files from this turn (after last user msg) + pending — not whole-session history. */
  const artifactNames = useMemo(() => {
    let lastUserIdx = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    const names: string[] = [];
    const seen = new Set<string>();
    const add = (name: string) => {
      const key = name.trim();
      if (!key || seen.has(key)) return;
      seen.add(key);
      names.push(key);
    };
    for (let i = lastUserIdx + 1; i < messages.length; i++) {
      for (const a of messages[i].artifacts ?? []) add(a.name);
    }
    for (const a of pendingArtifacts) add(a.name);
    return names;
  }, [messages, pendingArtifacts]);

  const steps = useMemo(
    () => buildWorkLogSteps(trace, artifactNames),
    [trace, artifactNames],
  );

  const stepThinks = useMemo(() => collectStepThinks(trace), [trace]);
  const thinkAssign = useMemo(
    () => assignThinksToSteps(stepThinks, steps),
    [stepThinks, steps],
  );

  const inflight = useMemo(() => findInFlightTool(trace), [trace]);

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
        confirmCount: confirmQueue?.length ?? 0,
        pendingArtifactCount: pendingArtifacts?.length ?? 0,
        thinkingSubject: thinking?.subject,
        hasPrepStep: steps.some((s) => s.kind === "prep"),
        quietMs,
        beating,
      }),
    [
      inflight,
      trace,
      taskInfo,
      taskRunning,
      confirmQueue?.length,
      pendingArtifacts?.length,
      thinking?.subject,
      steps,
      quietMs,
      beating,
    ],
  );
  const liveLabel = activity.label;
  const phaseHint = activity.phase;
  const liveElapsed =
    runStatus === "running" && inflight?.startedAtMs
      ? formatSplittingElapsed(now - inflight.startedAtMs)
      : runStatus === "running" && quietMs >= 4000
        ? formatSplittingElapsed(quietMs)
        : null;

  if (runStatus === "idle") return null;
  if (runStatus !== "running" && steps.length === 0 && elapsedMs < 1000) return null;

  const timeLabel = formatSplittingElapsed(elapsedMs);
  const running = runStatus === "running";
  const tokenLabel =
    budgetTokens > 0
      ? `${formatTokenCount(budgetTokens)} tokens`
      : running
        ? "0 tokens"
        : null;
  const tokenTitle =
    budgetMaxTokens > 0
      ? `本轮累计约 ${formatTokenCount(budgetTokens)} / ${formatTokenCount(budgetMaxTokens)} tokens（估算）`
      : undefined;

  return (
    <div
      className={cn("my-2 flex w-full min-w-0 flex-col", className)}
      role="status"
      aria-live="polite"
    >
      <button
        type="button"
        aria-expanded={outerOpen}
        onClick={() => setOuterOpen((v) => !v)}
        className="flex w-full min-w-0 items-center justify-start gap-1.5 px-0 py-2 text-left"
      >
        {running ? (
          <ThinkingOrb
            state={orbStateFromSubject(thinking?.subject ?? liveLabel)}
            size={20}
            theme="auto"
            aria-label={liveLabel}
            className="shrink-0"
          />
        ) : null}
        <span
          className="min-w-0 flex-1 text-body-sm font-medium text-ds-text-neutral-muted-default"
          title={running ? tokenTitle : undefined}
        >
          {running ? (
            <ShinyText
              text={`已工作 ${timeLabel}${tokenLabel ? ` · ${tokenLabel}` : ""}`}
              speed={2.2}
              className="max-w-full truncate tabular-nums"
            />
          ) : (
            <>
              已工作{" "}
              <span className="tabular-nums text-ds-text-neutral-subtle-default">
                {timeLabel}
              </span>
              {tokenLabel ? (
                <span
                  className="tabular-nums text-ds-text-neutral-subtle-default"
                  title={tokenTitle}
                >
                  {" "}
                  · {tokenLabel}
                </span>
              ) : null}
            </>
          )}
        </span>
        {outerOpen ? (
          <ChevronDown
            size={16}
            strokeWidth={2}
            aria-hidden
            className="shrink-0 text-ds-icon-neutral-muted-default"
          />
        ) : (
          <ChevronRight
            size={16}
            strokeWidth={2}
            aria-hidden
            className="shrink-0 text-ds-icon-neutral-muted-default"
          />
        )}
      </button>

      <div
        className={cn(
          "grid transition-[grid-template-rows,opacity] duration-200 ease-[cubic-bezier(0.32,0.72,0,1)]",
          outerOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
        aria-hidden={!outerOpen}
      >
        <div className="min-h-0 overflow-hidden">
            <div className="flex min-w-0 flex-col gap-1.5 pb-1 pl-0">
              {running ? (
                <div className="flex min-w-0 flex-col gap-0.5 py-0.5">
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.div
                      key={liveLabel}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.18 }}
                      className="flex min-w-0 items-baseline gap-1.5"
                    >
                      <ShinyText
                        text={liveLabel}
                        speed={2.4}
                        className="min-w-0 truncate text-body-sm"
                      />
                      {liveElapsed ? (
                        <span className="shrink-0 tabular-nums text-[11px] text-ds-text-neutral-subtle-default">
                          已 {liveElapsed}
                        </span>
                      ) : null}
                    </motion.div>
                  </AnimatePresence>
                  <span className="text-[11px] text-ds-text-neutral-subtle-default">
                    {phaseHint}
                  </span>
                </div>
              ) : null}

              {steps.length === 0 && running ? (
                <div className="flex items-center gap-2 py-1 text-body-sm text-ds-text-neutral-subtle-default">
                  <span className="inline-flex gap-0.5" aria-hidden>
                    <span className="h-1 w-1 animate-pulse rounded-full bg-ds-text-neutral-subtle-default" />
                    <span className="h-1 w-1 animate-pulse rounded-full bg-ds-text-neutral-subtle-default [animation-delay:150ms]" />
                    <span className="h-1 w-1 animate-pulse rounded-full bg-ds-text-neutral-subtle-default [animation-delay:300ms]" />
                  </span>
                  正在连接并准备执行…
                </div>
              ) : null}

              <AnimatePresence initial={false}>
                {steps.map((step) => {
                  if (step.kind === "file") {
                    return (
                      <motion.button
                        key={step.id}
                        type="button"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex w-full items-center gap-1.5 py-1 text-left text-body-sm font-medium text-ds-text-neutral-muted-default hover:underline"
                        onClick={() => {
                          const art =
                            messages
                              .flatMap((m) => m.artifacts ?? [])
                              .find((a) => a.name === step.detail) ||
                            pendingArtifacts.find((a) => a.name === step.detail);
                          if (!art) return;
                          usePageTabStore.getState().openPreviewFoldSide();
                          usePreviewStore.getState().openFile(art.path, art.name);
                        }}
                      >
                        <FileTypeIcon
                          pathOrName={step.detail || step.label}
                          size="sm"
                        />
                        <span className="truncate">{step.label}</span>
                        <ChevronRight
                          size={14}
                          strokeWidth={2}
                          aria-hidden
                          className="ml-auto shrink-0 text-ds-icon-neutral-muted-default"
                        />
                      </motion.button>
                    );
                  }
                  const isRunning = running && step.status === "running";
                  const thinks = thinkAssign.byStep.get(step.id) ?? [];
                  if (step.kind === "tool") {
                    return (
                      <ToolStepCard
                        key={step.id}
                        step={step}
                        isRunning={isRunning}
                        thinks={thinks}
                        running={running}
                      />
                    );
                  }
                  const line = formatWorkLogLine(step.label, step.detail);
                  return (
                    <motion.div
                      key={step.id}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={cn(
                        "flex min-w-0 flex-col gap-0.5",
                        !isRunning && "opacity-70",
                      )}
                    >
                      <div className="flex min-w-0 items-center gap-2 py-0.5 text-body-sm text-ds-text-neutral-muted-default">
                        <span
                          className={cn(
                            "h-1.5 w-1.5 shrink-0 rounded-full",
                            isRunning
                              ? "bg-[var(--colors-green-default,#22c55e)] shadow-[0_0_0_3px_rgba(34,197,94,0.2)]"
                              : "bg-ds-border-neutral-default-default",
                          )}
                          aria-hidden
                        />
                        <span
                          className={cn(
                            "min-w-0 truncate",
                            !isRunning && "text-ds-text-neutral-subtle-default",
                          )}
                        >
                          {isRunning ? (
                            <ShinyText
                              text={line}
                              speed={2.6}
                              className="truncate text-body-sm"
                            />
                          ) : (
                            line
                          )}
                        </span>
                      </div>
                      <StepThinkList thinks={thinks} running={running} />
                    </motion.div>
                  );
                })}
              </AnimatePresence>
              {thinkAssign.leftover.length > 0 ? (
                <StepThinkList thinks={thinkAssign.leftover} running={running} />
              ) : null}
            </div>
        </div>
      </div>
    </div>
  );
}
