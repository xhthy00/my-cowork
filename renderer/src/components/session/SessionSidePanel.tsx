/**
 * Adapted from eigent: SessionSidePanel + SingleAgentSidePanel
 * + ProgressSection / ExecutionContextSection / AgentFolderSection
 */
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Workflow,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  SESSION_SIDE_PANEL_EXPANDED_OUTER_CLASS,
  SESSION_SIDE_PANEL_FOLDED_OUTER_CLASS,
} from "@/components/session/sessionSidePanelLayout";
import {
  CategoryLabel,
  CountPill,
  ProgressCircle,
  SidePanelListRow,
} from "@/components/session/sidePanelPrimitives";
import { AgentPoolBody } from "@/components/session/AgentPoolSection";
import TracePanel from "@/components/TracePanel";
import FileTypeIcon from "@/components/files/FileTypeIcon";
import { SessionModeToggle } from "@/components/workforce/WorkforceSidePanel";
import {
  buildContextItems,
  buildProgressItems,
} from "@/lib/progressFromTrace";
import { isVisibleAgentPath } from "@/lib/outputFiles";
import {
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
        if (!decoded || seen.has(decoded) || !isVisibleAgentPath(decoded)) {
          continue;
        }
        seen.add(decoded);
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
    () => buildProgressItems(taskInfo, trace, runDone),
    [taskInfo, trace, runDone],
  );

  const contextItems = useMemo(
    () => buildContextItems(
      trace,
      files.map((f) => f.name),
    ),
    [trace, files],
  );

  const headerTitle = mode === SessionMode.SINGLE_AGENT ? "单智能体" : "多智能体";

  return (
    <aside
      className={cn(
        "relative flex h-full shrink-0 flex-col overflow-hidden bg-transparent transition-[width] duration-200",
        visible ? SESSION_SIDE_PANEL_EXPANDED_OUTER_CLASS : SESSION_SIDE_PANEL_FOLDED_OUTER_CLASS,
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
          <div className="flex h-11 shrink-0 items-center gap-2 px-2">
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

          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
            {mode === SessionMode.WORKFORCE && (
              <AccordionBox title="智能体池" defaultOpen={false}>
                {({ open }) => <AgentPoolBody agents={agents} open={open} />}
              </AccordionBox>
            )}

            <AccordionBox
              title="进度"
              titleSuffix={
                progressItems.length > 0 ? <CountPill count={progressItems.length} /> : null
              }
            >
              {progressItems.length === 0 ? (
                <div className="px-1 py-1 text-body-sm text-ds-text-neutral-subtle-default opacity-60">
                  {runStatus === "running"
                    ? "正在规划步骤…"
                    : "任务运行时，在此跟踪计划步骤与状态。"}
                </div>
              ) : (
                <ul className="m-0 list-none space-y-0.5 p-0">
                  {progressItems.map((task) => {
                    const done = task.status === "completed";
                    const running = !done && task.status === "running";
                    return (
                      <li key={task.id}>
                        <SidePanelListRow
                          className="hover:bg-ds-bg-neutral-subtle-default"
                          leading={<ProgressCircle done={done} running={running} />}
                        >
                          <span
                            className={cn(
                              done && "line-through text-ds-text-neutral-subtle-default",
                              running && "font-medium",
                            )}
                          >
                            {task.content}
                          </span>
                        </SidePanelListRow>
                      </li>
                    );
                  })}
                </ul>
              )}
            </AccordionBox>

            <AccordionBox
              title="执行上下文"
            >
              {contextItems.length === 0 ? (
                <div className="px-1 py-1 text-body-sm text-ds-text-neutral-subtle-default opacity-60">
                  跟踪本任务使用的技能、MCP 与引用文件。
                </div>
              ) : (
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
              )}
            </AccordionBox>

            <AccordionBox
              title="Trace"
              defaultOpen={false}
              titleSuffix={
                trace.length > 0 ? <CountPill count={trace.length} /> : null
              }
            >
              <TracePanel embedded />
            </AccordionBox>

            <AccordionBox title="输出文件夹">
              {files.length === 0 ? (
                <div className="px-1 py-1 text-body-sm text-ds-text-neutral-subtle-default opacity-60">
                  最终交付文件会显示在这里。
                </div>
              ) : (
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
              )}
            </AccordionBox>
          </div>
        </>
      )}
    </aside>
  );
}
