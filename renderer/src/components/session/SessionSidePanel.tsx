/**
 * Adapted from eigent: SessionSidePanel + SingleAgentSidePanel
 * + ProgressSection / ExecutionContextSection / AgentFolderSection
 */
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  SESSION_SIDE_PANEL_EXPANDED_OUTER_CLASS,
  SESSION_SIDE_PANEL_FOLDED_OUTER_CLASS,
} from "@/components/session/sessionSidePanelLayout";
import {
  CategoryLabel,
  CountPill,
  SidePanelListRow,
} from "@/components/session/sidePanelPrimitives";
import { AgentPoolBody } from "@/components/session/AgentPoolSection";
import TracePanel from "@/components/TracePanel";
import FileTypeIcon from "@/components/files/FileTypeIcon";
import { SessionModeToggle } from "@/components/workforce/WorkforceSidePanel";
import {
  buildContextItems,
  buildProgressItems,
  buildStepExecutionDetails,
} from "@/lib/progressFromTrace";
import { isVisibleAgentPath } from "@/lib/outputFiles";
import {
  artifactIdentity,
  decodeUnicodeEscapes,
  fileBasename,
  isCorruptBasename,
} from "@/lib/fsPath";
import { cn } from "@/lib/utils";
import { usePageTabStore } from "@/store/pageTab";
import { usePreviewStore } from "@/store/preview";
import { useSessionStore } from "@/store/session";
import { useWorkforceStore } from "@/store/workforce";
import { SessionMode } from "@/types/workforce";

function AccordionBox({
  title,
  titleSuffix,
  defaultOpen = true,
  children,
}: {
  title: string;
  titleSuffix?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode | ((state: { open: boolean }) => ReactNode);
}) {
  const [open, setOpen] = useState(defaultOpen);
  const isRenderProp = typeof children === "function";
  const dynamicBody = isRenderProp
    ? (children as (s: { open: boolean }) => ReactNode)({ open })
    : null;

  return (
    <div className="z-10 flex min-w-0 shrink-0 flex-col overflow-hidden rounded-xl border border-solid border-ds-border-neutral-subtle-disabled bg-ds-bg-neutral-default-default">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full shrink-0 items-center justify-between gap-2 px-3 py-2.5 text-left transition-colors hover:bg-ds-bg-neutral-default-hover"
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-body-sm font-semibold text-ds-text-neutral-default-default">
            {title}
          </span>
          {titleSuffix ? (
            <span className="flex shrink-0 items-center">{titleSuffix}</span>
          ) : null}
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-ds-text-neutral-muted-default transition-transform duration-200",
            open ? "rotate-0" : "-rotate-90",
          )}
        />
      </button>
      {isRenderProp ? (
        dynamicBody != null ? (
          <div className="min-w-0 px-2 pb-3">{dynamicBody}</div>
        ) : null
      ) : open ? (
        <div className="min-w-0 px-2 pb-3">{children as ReactNode}</div>
      ) : null}
    </div>
  );
}

export default function SessionSidePanel() {
  const visible = usePageTabStore((s) => s.sidePanelVisible);
  const setVisible = usePageTabStore((s) => s.setSidePanelVisible);
  const mode = useWorkforceStore((s) => s.sessionMode);
  const agents = useWorkforceStore((s) => s.taskAssigning);
  const taskInfo = useWorkforceStore((s) => s.taskInfo);
  const planRevision = useWorkforceStore((s) => s.planRevision);
  const revisionReason = useWorkforceStore((s) => s.revisionReason);

  const trace = useSessionStore((s) => s.trace);
  const messages = useSessionStore((s) => s.messages);
  const pendingArtifacts = useSessionStore((s) => s.pendingArtifacts);
  const runStatus = useSessionStore((s) => s.runStatus);
  const runDone = runStatus === "done" || runStatus === "error";

  // Final deliverables: confirmed message artifacts + in-flight pending writes.
  const files = useMemo(() => {
    const out: { name: string; path: string }[] = [];
    const seen = new Set<string>();
    const pushPath = (raw: string, nameHint?: string) => {
      const lines = raw
        .split(/[\r\n]+/)
        .map((l) => l.trim())
        .filter(Boolean);
      for (const p of lines) {
        const decoded = decodeUnicodeEscapes(p);
        const id = artifactIdentity(decoded);
        if (!decoded || !id || seen.has(id) || !isVisibleAgentPath(decoded)) {
          continue;
        }
        seen.add(id);
        const base = fileBasename(decoded);
        const label =
          nameHint && !isCorruptBasename(nameHint) ? nameHint : base || decoded;
        out.push({
          name: label,
          path: decoded,
        });
      }
    };
    for (const m of messages) {
      for (const a of m.artifacts ?? []) {
        pushPath(a.path, a.name);
      }
    }
    for (const a of pendingArtifacts) {
      pushPath(a.path, a.name);
    }
    return out;
  }, [messages, pendingArtifacts]);

  const progressItems = useMemo(
    () => buildProgressItems(taskInfo),
    [taskInfo],
  );
  const executionDetails = useMemo(
    () => buildStepExecutionDetails(trace, taskInfo),
    [trace, taskInfo],
  );
  const [expandedStepId, setExpandedStepId] = useState<string | null>(null);
  const activeStepId = progressItems.find((item) => item.status === "running")?.id ?? null;
  useEffect(() => {
    if (activeStepId) setExpandedStepId(activeStepId);
  }, [activeStepId]);
  const completedGlobal = progressItems.filter((item) => item.status === "completed").length;

  const contextItems = useMemo(
    () => buildContextItems(
      trace,
      files.map((f) => f.name),
    ),
    [trace, files],
  );
  const hasProgress = progressItems.length > 0;
  const hasContext = contextItems.length > 0;
  const hasTrace = trace.length > 0;
  const hasFiles = files.length > 0;
  const hasDetails = hasProgress || hasContext || hasTrace || hasFiles;

  const headerTitle = mode === SessionMode.SINGLE_AGENT ? "单智能体" : "多智能体";

  return (
    <aside
      className={cn(
        "relative flex h-full shrink-0 flex-col overflow-hidden bg-transparent transition-[width] duration-200",
        visible
          ? !hasDetails && mode === SessionMode.SINGLE_AGENT
            ? "w-[min(280px,32vw)]"
            : SESSION_SIDE_PANEL_EXPANDED_OUTER_CLASS
          : SESSION_SIDE_PANEL_FOLDED_OUTER_CLASS,
        !visible && "rounded-l-xl",
      )}
    >
      {!visible ? (
        <button
          type="button"
          className="flex h-full w-full flex-col items-center gap-2 rounded-l-xl bg-ds-bg-neutral-default-default pt-3 text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default"
          onClick={() => setVisible(true)}
          title="展开侧栏"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      ) : (
        <>
          <div className="flex h-11 shrink-0 items-center gap-2 px-1">
            <Workflow className="h-4 w-4 text-ds-icon-neutral-muted-default" />
            <span className="text-body-sm font-semibold text-ds-text-neutral-default-default">
              {headerTitle}
            </span>
            <div className="flex-1" />
            <SessionModeToggle />
            <Button size="icon" variant="ghost" title="折叠" onClick={() => setVisible(false)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-y-auto px-1 pb-2">
            {!hasDetails && (
              <div className="rounded-xl border border-ds-border-neutral-subtle-disabled bg-ds-bg-neutral-default-default px-3 py-3">
                <p className="m-0 text-body-sm font-semibold text-ds-text-neutral-default-default">
                  {runStatus === "running" ? "正在整理任务信息" : "暂无运行详情"}
                </p>
                <p className="mb-0 mt-1 text-body-sm text-ds-text-neutral-muted-default">
                  {runStatus === "running"
                    ? "计划步骤和执行记录生成后会显示在这里。"
                    : runDone || messages.length > 0
                      ? "本次任务没有可展示的进度、执行记录或交付文件。"
                      : "开始任务后，可在这里查看进度、执行记录与交付文件。"}
                </p>
              </div>
            )}
            {mode === SessionMode.WORKFORCE && (
              <AccordionBox title="智能体池" defaultOpen={false}>
                {({ open }) => <AgentPoolBody agents={agents} open={open} />}
              </AccordionBox>
            )}

            {(hasProgress || runStatus === "running") && <AccordionBox
              title="进度"
              titleSuffix={hasProgress
                ? <span className="progress-header-count">{completedGlobal} / {progressItems.length}</span>
                : undefined}
            >
              {planRevision > 1 && revisionReason && (
                <div className="progress-revision" role="status">
                  计划已更新<span aria-hidden="true"> · </span>{revisionReason}
                </div>
              )}
              {hasProgress && (
                <div className="progress-overview">
                  <div className="progress-overview-label">
                    <span>全局步骤</span>
                    <strong>{Math.round((completedGlobal / progressItems.length) * 100)}%</strong>
                  </div>
                  <div
                    className="progress-overview-track"
                    role="progressbar"
                    aria-label="全局步骤完成进度"
                    aria-valuemin={0}
                    aria-valuemax={progressItems.length}
                    aria-valuenow={completedGlobal}
                  >
                    <span style={{ width: `${(completedGlobal / progressItems.length) * 100}%` }} />
                  </div>
                </div>
              )}
              {!hasProgress && (
                <p className="progress-empty">正在规划全局步骤…</p>
              )}
              <ol className="progress-step-list">
                  {progressItems.map((task, index) => {
                    const done = task.status === "completed";
                    const running = !done && task.status === "running";
                    const details = executionDetails[task.id] || [];
                    const hasChildren = task.substeps.length > 0 || details.length > 0;
                    const expanded = expandedStepId === task.id;
                    const completedChildren = task.substeps.filter((child) => child.status === "completed").length;
                    const statusLabel = done ? "已完成" : running ? "进行中" : task.status === "failed" ? "失败" : "待执行";
                    return (
                      <li key={task.id} className="progress-step" data-status={task.status} data-expanded={expanded}>
                        <button
                          type="button"
                          className="progress-step-trigger"
                          onClick={() => hasChildren && setExpandedStepId(expanded ? null : task.id)}
                          disabled={!hasChildren}
                          aria-expanded={hasChildren ? expanded : undefined}
                          aria-label={`步骤 ${index + 1}：${task.content}，${statusLabel}${task.substeps.length > 0 ? `，分步 ${completedChildren} / ${task.substeps.length}` : ""}`}
                        >
                          <span className="progress-step-index" aria-hidden="true">
                            {done ? <Check size={13} strokeWidth={2.7} /> : task.status === "failed" ? <AlertCircle size={15} /> : String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="progress-step-copy">
                            <span className="progress-step-title">{task.content}</span>
                            {task.substeps.length > 0 && <span className="progress-step-meta">分步 {completedChildren}/{task.substeps.length}</span>}
                          </span>
                          <span className="progress-step-state" aria-hidden="true">{statusLabel}</span>
                          {hasChildren && <ChevronDown className={cn("progress-step-chevron", expanded && "is-expanded")} size={14} aria-hidden="true" />}
                        </button>
                        {expanded && hasChildren && (
                          <div className="progress-step-body">
                            {task.substeps.length > 0 && <ol className="progress-substep-list">
                              {task.substeps.map((child) => <li key={child.id} className="progress-substep" data-status={child.status}>
                                <span className="progress-substep-marker" aria-hidden="true">
                                  {child.status === "completed" ? <Check size={10} strokeWidth={3} /> : child.status === "failed" ? <AlertCircle size={13} /> : null}
                                </span>
                                <span className="progress-substep-title">{child.content}</span>
                                <span className="sr-only">{child.status === "completed" ? "已完成" : child.status === "running" ? "进行中" : child.status === "failed" ? "失败" : "待执行"}</span>
                              </li>)}
                            </ol>}
                            {details.length > 0 && (
                              <div className="progress-execution">
                                <p className="progress-execution-heading">执行明细 <span>{details.length}</span></p>
                                {details.slice(-4).map((detail) => <p key={detail.id} className="progress-execution-row"><span aria-hidden="true">{detail.done ? "✓" : "◌"}</span><span className="truncate">{detail.label}</span></p>)}
                              </div>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
              </ol>
            </AccordionBox>}

            {hasContext && <AccordionBox
              title="执行上下文"
            >
              <div className="flex flex-col gap-2">
                  {(["skill", "connector", "file"] as const).map((cat) => {
                    const group = contextItems.filter((i) => i.category === cat);
                    if (!group.length) return null;
                    const label =
                      cat === "skill"
                        ? "技能"
                        : cat === "connector"
                          ? "MCP 工具"
                          : "引用文件";
                    return (
                      <div key={cat} className="flex flex-col">
                        <CategoryLabel>{label}</CategoryLabel>
                        <ul className="m-0 list-none space-y-0.5 p-0">
                          {group.map((item) => (
                            <li key={item.id}>
                              <SidePanelListRow
                                leading={
                                  <FileText className="h-3.5 w-3.5 text-ds-icon-neutral-muted-default" />
                                }
                                interactiveHover
                                onClick={() => {
                                  if (cat === "skill") {
                                    window.dispatchEvent(
                                      new CustomEvent("my-cowork:navigate", {
                                        detail: "skills",
                                      }),
                                    );
                                  }
                                }}
                              >
                                {item.label}
                              </SidePanelListRow>
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
              </div>
            </AccordionBox>}

            {hasTrace && <AccordionBox
              title="Trace"
              defaultOpen={false}
              titleSuffix={<CountPill count={trace.length} />}
            >
              <TracePanel embedded />
            </AccordionBox>}

            {hasFiles && <AccordionBox title="输出文件夹">
              <ul className="m-0 list-none space-y-0.5 p-0">
                  {files.map((f) => (
                    <li key={f.path}>
                      <SidePanelListRow
                        leading={<FileTypeIcon pathOrName={f.name} size="sm" />}
                        onClick={() => {
                          usePageTabStore.getState().openPreviewFoldSide();
                          usePreviewStore.getState().openFile(f.path, f.name);
                        }}
                      >
                        {f.name}
                      </SidePanelListRow>
                    </li>
                  ))}
              </ul>
            </AccordionBox>}
          </div>
        </>
      )}
    </aside>
  );
}
