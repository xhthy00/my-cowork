/**
 * Adapted from eigent: Workspace composer + Session ChatBox.
 * Empty: welcome hero · title · composer · Recent runs
 * Active: message list + follow-up composer
 */
import { ArrowRight, CheckCircle2, ChevronDown, Copy, Eye, Loader2, Sparkles, Square, SquareArrowOutUpRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import welcomeHero from "@/assets/welcome/chat-welcome-hero.webp";
import welcomeHeroWorkforce from "@/assets/welcome/chat-welcome-hero-workforce.webp";
import { abortChatStream } from "../api/chatStream";
import type { SSEvent } from "../api/sse";
import GridPatternBackground from "./Background/GridPatternBackground";
import ChatBar from "./chat/ChatBar";
import ChatConfirmCard, { ChatConfirmRecordGroup } from "./chat/ChatConfirmCard";
import WorkspaceOverlaysBar from "./workspace/WorkspaceOverlaysBar";
import OnboardingHint from "./workspace/OnboardingHint";
import MessageContent from "./chat/MessageContent";
import { UserMessageRichContent } from "./chat/UserMessageRichContent";
import PlanTaskBox from "./chat/PlanTaskBox";
import WorkLogAccordion from "./chat/WorkLogAccordion";
import ComposerLiveStatus from "./chat/ComposerLiveStatus";
import FileTypeIcon, { extOfPath, fileTypeMeta } from "./files/FileTypeIcon";
import { Button } from "./ui/button";
import type { FileArtifact, Message } from "../store/session";
import { resolveEndMessageText, useSessionStore } from "../store/session";
import { dispatchProjectEvent, getProjectTaskId } from "../store/livePark";
import { getProjectRuntime } from "../store/projectRuntime";
import { isVisibleAgentPath } from "@/lib/outputFiles";
import { fileBasename, isCorruptBasename, normalizeFsPath } from "@/lib/fsPath";
import { cn } from "@/lib/utils";
import { usePreviewStore } from "../store/preview";
import { usePageTabStore } from "../store/pageTab";
import { useSessionsStore } from "../store/sessions";
import { useWorkforceStore } from "../store/workforce";
import { planTodosFromQuery } from "../lib/planTodos";
import {
  displayTitleFromUserContent,
  fileNameFromPath,
  parseUserAttachments,
} from "../lib/userAttachments";
import { SessionMode } from "../types/workforce";

/** Adapted from eigent / Claude-style artifact card: type badge + name + ext. */
function ArtifactChip({ artifact }: { artifact: FileArtifact }) {
  const path = normalizeFsPath(artifact.path) || artifact.path;
  const name =
    artifact.name && !isCorruptBasename(artifact.name)
      ? artifact.name
      : fileBasename(path) || artifact.name;
  const ext = extOfPath(name) || artifact.kind;
  const meta = fileTypeMeta(name, artifact.kind);
  return (
    <button
      type="button"
      className="group flex max-w-full min-w-[200px] cursor-pointer items-center gap-2.5 rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 py-2.5 text-left shadow-[var(--shadow-button)] transition-colors hover:border-ds-border-neutral-default-default hover:bg-ds-bg-neutral-default-hover"
      title={path}
      onClick={() => {
        usePageTabStore.getState().openPreviewFoldSide();
        usePreviewStore.getState().openFile(path, name);
      }}
    >
      <FileTypeIcon pathOrName={name} hint={artifact.kind} size="md" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold text-ds-text-neutral-default-default">
          {name}
        </div>
        <div className="mt-0.5 text-[11px] text-ds-text-neutral-subtle-default">
          {meta.label}
          {ext ? ` · .${ext}` : ""}
        </div>
      </div>
      <SquareArrowOutUpRight className="h-3.5 w-3.5 shrink-0 text-ds-icon-neutral-muted-default opacity-60 transition-opacity group-hover:opacity-100" />
    </button>
  );
}

/** Adapted from eigent: UserMessageCard attaches — filename only, path on hover. */
function UserAttachmentChip({ path }: { path: string }) {
  const name = fileNameFromPath(path);
  return (
    <button
      type="button"
      className="flex max-w-[180px] cursor-pointer items-center gap-1.5 rounded-lg bg-ds-bg-neutral-default-default px-1.5 py-1 text-left transition-colors hover:bg-ds-bg-neutral-default-hover"
      title={path}
      onClick={() => {
        usePageTabStore.getState().openPreviewFoldSide();
        usePreviewStore.getState().openFile(path, name);
      }}
    >
      <FileTypeIcon pathOrName={name} size="sm" />
      <span className="min-w-0 truncate font-['Inter'] text-xs font-bold text-ds-text-neutral-default-default">
        {name}
      </span>
    </button>
  );
}

function UserMessageBubble({ content }: { content: string }) {
  const { text, paths } = useMemo(
    () => parseUserAttachments(content),
    [content],
  );
  const openBrowser = usePreviewStore((s) => s.openBrowser);
  const openPreviewFoldSide = usePageTabStore((s) => s.openPreviewFoldSide);
  const setPreviewOpen = usePageTabStore((s) => s.setPreviewOpen);
  if (!text && paths.length === 0) return null;
  return (
    <div className="msg user">
      <div className="flex min-w-0 flex-col items-end">
        {paths.length > 0 ? (
          <div className="mb-1.5 flex flex-wrap justify-end gap-1">
            {paths.map((p) => (
              <UserAttachmentChip key={p} path={p} />
            ))}
          </div>
        ) : null}
        {text ? (
          <div className="bubble whitespace-pre-wrap text-[16px] leading-[1.65] text-ds-text-neutral-default-default">
            <UserMessageRichContent
              content={text}
              onOpenUrl={(url) => {
                openBrowser(url);
                openPreviewFoldSide();
                setPreviewOpen(true);
              }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * AionUi formatMessageTime: Today "HH:mm", older "MM-DD HH:mm".
 */
export const formatMessageTime = (timestamp: number): string => {
  const date = new Date(timestamp);
  const now = new Date();
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const time = `${hours}:${minutes}`;

  if (
    date.getFullYear() !== now.getFullYear() ||
    date.getMonth() !== now.getMonth() ||
    date.getDate() !== now.getDate()
  ) {
    const month = (date.getMonth() + 1).toString().padStart(2, "0");
    const day = date.getDate().toString().padStart(2, "0");
    return `${month}-${day} ${time}`;
  }
  return time;
};

/** AionUi-style hover-revealed copy + timestamp row beneath a message. */
function MessageCopyRow({
  text,
  ts,
  align,
}: {
  text: string;
  ts?: number;
  align: "left" | "right";
}) {
  const [copied, setCopied] = useState(false);
  if (!text.trim() && !ts) return null;
  return (
    <div
      className={cn(
        "mt-1 flex h-8 items-center gap-2",
        align === "right" ? "flex-row-reverse" : "flex-row",
      )}
    >
      <button
        type="button"
        title={copied ? "已复制" : "复制"}
        className="cursor-pointer rounded p-1 opacity-0 transition-opacity hover:bg-ds-bg-neutral-default-default group-hover:opacity-100"
        style={{ lineHeight: 0 }}
        onClick={() => {
          void navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
          });
        }}
      >
        <Copy className="h-4 w-4 text-ds-text-neutral-subtle-default" />
      </button>
      {ts ? (
        <span className="select-none text-xs text-ds-text-neutral-subtle-default opacity-0 transition-opacity group-hover:opacity-100">
          {formatMessageTime(ts)}
        </span>
      ) : null}
    </div>
  );
}

type Turn = {
  user: Message;
  assistants: Message[];
};

function groupTurns(messages: Message[]): Turn[] {
  const turns: Turn[] = [];
  let current: Turn | null = null;
  for (const m of messages) {
    if (m.role === "user") {
      current = { user: m, assistants: [] };
      turns.push(current);
    } else if (current) {
      current.assistants.push(m);
    } else {
      current = {
        user: { id: `synthetic-${m.id}`, role: "user", content: "" },
        assistants: [m],
      };
      turns.push(current);
    }
  }
  return turns;
}

function mergeAssistantContent(assistants: Message[]): {
  content: string;
  artifacts: FileArtifact[];
  id: string;
  createdAt?: number;
} {
  const parts: string[] = [];
  const artifacts: FileArtifact[] = [];
  const seen = new Set<string>();
  for (const m of assistants) {
    // Keep 印记 markers for MessageContent; do not strip to formal-only here.
    const text = m.content?.trim();
    if (text) parts.push(text);
    for (const a of m.artifacts ?? []) {
      if (!isVisibleAgentPath(a.path) && !isVisibleAgentPath(normalizeFsPath(a.path))) {
        continue;
      }
      const path = normalizeFsPath(a.path) || a.path;
      if (seen.has(path)) continue;
      seen.add(path);
      const name =
        a.name && !isCorruptBasename(a.name) ? a.name : fileBasename(path) || a.name;
      artifacts.push({ ...a, path, name });
    }
  }
  return {
    id: assistants[assistants.length - 1]?.id ?? "assistant",
    content: parts.join("\n\n"),
    artifacts,
    createdAt: assistants[assistants.length - 1]?.createdAt,
  };
}

/** Collect deliverable artifacts across all assistant messages in a turn. */
function collectArtifacts(
  assistants: Message[],
  extra: FileArtifact[] = [],
): FileArtifact[] {
  const artifacts: FileArtifact[] = [];
  const seen = new Set<string>();
  const push = (a: FileArtifact) => {
    if (!isVisibleAgentPath(a.path) && !isVisibleAgentPath(normalizeFsPath(a.path))) {
      return;
    }
    const path = normalizeFsPath(a.path) || a.path;
    if (seen.has(path)) return;
    seen.add(path);
    const name =
      a.name && !isCorruptBasename(a.name) ? a.name : fileBasename(path) || a.name;
    artifacts.push({ ...a, path, name });
  };
  for (const m of assistants) {
    for (const a of m.artifacts ?? []) push(a);
  }
  for (const a of extra) push(a);
  return artifacts;
}

function AssistantBody({ content, streaming }: { content: string; streaming?: boolean }) {
  const text = resolveEndMessageText(content) || content.trim();
  if (!text) return null;
  return (
    <div className="msg assistant w-full">
      <div className="flex w-full min-w-0 flex-col overflow-hidden">
        <MessageContent content={text} role="assistant" hideThink verbatim />
        {streaming ? (
          <span
            aria-hidden
            className="mt-1 inline-block h-[1.05em] w-[2px] translate-y-px bg-ds-text-neutral-primary-default align-text-bottom"
            style={{ animation: "pulse 1s ease-in-out infinite" }}
          />
        ) : null}
      </div>
    </div>
  );
}

function AssistantTimeline({
  assistants,
  streaming,
}: {
  assistants: Message[];
  streaming?: boolean;
}) {
  const nodes: ReactNode[] = [];
  let i = 0;
  while (i < assistants.length) {
    const msg = assistants[i];
    if (msg.confirm && msg.confirm.status !== "pending") {
      const group: Message[] = [];
      while (
        i < assistants.length &&
        assistants[i].confirm &&
        assistants[i].confirm!.status !== "pending"
      ) {
        group.push(assistants[i]);
        i++;
      }
      nodes.push(
        <ChatConfirmRecordGroup
          key={group[0].id}
          confirms={group.map((m) => m.confirm!)}
        />,
      );
      for (const m of group) {
        const text = m.content?.trim();
        if (!text) continue;
        nodes.push(
          <AssistantBody key={`${m.id}-body`} content={text} streaming={streaming} />,
        );
      }
      continue;
    }
    if (msg.confirm) {
      nodes.push(<ChatConfirmCard key={msg.id} confirm={msg.confirm} />);
      const leaked = msg.content?.trim();
      if (leaked) {
        nodes.push(
          <AssistantBody key={`${msg.id}-body`} content={leaked} streaming={streaming} />,
        );
      }
      i++;
      continue;
    }
    const content = msg.content?.trim();
    if (content) {
      nodes.push(
        <AssistantBody key={msg.id} content={content} streaming={streaming} />,
      );
    }
    i++;
  }
  return <>{nodes}</>;
}

function bindChatHandlers(
  handleEvent: ReturnType<typeof useSessionStore.getState>["handleEvent"],
  addUserMessage: (t: string) => void,
  beginRun: () => void,
  activeId: string | null,
  touchSession: (id: string, patch?: Parameters<ReturnType<typeof useSessionsStore.getState>["touchSession"]>[1]) => void,
  messages: { role: string; content: string }[],
) {
  return {
    onEvent: (ev: SSEvent, projectId?: string) => {
      const pid = projectId || activeId;
      if (pid) dispatchProjectEvent(pid, ev);
      else handleEvent(ev);
      if (ev.type === "graph.start" && pid) {
        const firstUser = messages.find((x) => x.role === "user")?.content || "";
        touchSession(pid, {
          title: displayTitleFromUserContent(firstUser),
        });
      }
    },
    onSend: (text: string) => {
      if (activeId) {
        const rt = getProjectRuntime(activeId);
        rt.session.getState().addUserMessage(text);
        rt.session.getState().beginRun();
        rt.workforce.getState().seedPlan(planTodosFromQuery(text));
        touchSession(activeId, {
          title: displayTitleFromUserContent(text),
          status: "running",
        });
        return;
      }
      addUserMessage(text);
      beginRun();
      useWorkforceStore.getState().seedPlan(planTodosFromQuery(text));
    },
  };
}

export default function ChatView() {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const nearBottomRef = useRef(true);
  const wasRunningRef = useRef(false);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const messages = useSessionStore((s) => s.messages);
  const confirmQueueLen = useSessionStore((s) => s.confirmQueue.length);
  const confirmCallId = useSessionStore((s) => s.confirmQueue[0]?.call_id);
  const addUserMessage = useSessionStore((s) => s.addUserMessage);
  const beginRun = useSessionStore((s) => s.beginRun);
  const handleEvent = useSessionStore((s) => s.handleEvent);
  const runStatus = useSessionStore((s) => s.runStatus);
  const pendingArtifacts = useSessionStore((s) => s.pendingArtifacts);
  const previewOpen = usePageTabStore((s) => s.previewOpen);
  const openPreviewFoldSide = usePageTabStore((s) => s.openPreviewFoldSide);
  const setPreviewOpen = usePageTabStore((s) => s.setPreviewOpen);
  const setSidePanelVisible = usePageTabStore((s) => s.setSidePanelVisible);
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const addChooser = usePreviewStore((s) => s.addChooser);
  const setPreviewStoreOpen = usePreviewStore((s) => s.setOpen);
  const touchSession = useSessionsStore((s) => s.touchSession);
  const activeId = useSessionsStore((s) => s.activeId);
  const sessions = useSessionsStore((s) => s.sessions);
  const setActive = useSessionsStore((s) => s.setActive);
  const sessionMode = useWorkforceStore((s) => s.sessionMode);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    // AionUi behavior: only auto-follow the stream while the user is near the bottom.
    // Use an instant scroll instead of `scrollIntoView({ behavior: "smooth" })`:
    // during token streaming the container grows continuously, so restarting a smooth
    // animation on every update can never catch up — the view gets stuck mid-way with
    // older messages scrolled out at the top and the latest ones hidden below the fold.
    if (nearBottomRef.current && messagesScrollRef.current) {
      messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
    }
  }, [messages, confirmQueueLen, confirmCallId]);

  // When a run ends, the composer shrinks (status row / ThoughtDisplay unmount), which
  // grows the messages viewport. Re-pin to the bottom so the final answer is fully
  // visible instead of leaving the view truncated behind the collapsed composer.
  useEffect(() => {
    const running = runStatus === "running";
    if (wasRunningRef.current && !running && nearBottomRef.current) {
      const el = messagesScrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    }
    wasRunningRef.current = running;
  }, [runStatus]);

  function handleMessagesScroll() {
    const el = messagesScrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    nearBottomRef.current = near;
    setShowScrollBottom(!near);
  }

  useEffect(() => {
    setPreviewStoreOpen(previewOpen);
  }, [previewOpen, setPreviewStoreOpen]);

  async function stopTask() {
    setStopping(true);
    const taskId = activeId ? getProjectTaskId(activeId) : undefined;
    try {
      const backendUrl = await window.api.getBackendUrl();
      if (backendUrl) {
        await fetch(`${backendUrl}/api/chat/stop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(taskId ? { task_id: taskId } : {}),
        });
      }
    } catch {
      /* ignore */
    } finally {
      setStopping(false);
      // Keep SSE open for graph.end (Eigent skip-task). Abort only if still running.
      if (taskId) {
        window.setTimeout(() => {
          if (useSessionStore.getState().runStatus === "running") {
            abortChatStream(taskId);
            useSessionStore.setState({
              runStatus: "done",
              taskStartedAt: null,
            });
            if (activeId) touchSession(activeId, { status: "idle" });
          }
        }, 10_000);
      } else {
        if (activeId) touchSession(activeId, { status: "idle" });
        useSessionStore.setState({
          runStatus: "done",
          taskStartedAt: null,
        });
      }
    }
  }

  const handlers = bindChatHandlers(
    handleEvent,
    addUserMessage,
    beginRun,
    activeId,
    touchSession,
    messages,
  );

  const activeProject = sessions.find((s) => s.id === activeId);
  const boundAssistant = Boolean(activeProject?.assistantId);
  const assistantLabel =
    activeProject?.assistantName || activeProject?.title || "办公助手";
  const title = boundAssistant
    ? assistantLabel
    : "MyCowork 轻松搞定工作每一件事！";
  const skillIds = activeProject?.enabledSkillIds ?? [];
  const assistantPrompts = activeProject?.assistantPrompts ?? [];

  const recent = sessions.filter((s) => s.id !== activeId || s.status !== "idle").slice(0, 5);
  const turns = useMemo(() => groupTurns(messages), [messages]);

  if (messages.length === 0) {
    const recentPreview = recent.slice(0, 3);
    return (
      <section className="main relative z-[1] flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <GridPatternBackground />
        <div className="relative z-[1] mx-auto flex h-full w-full max-w-[560px] min-h-0 flex-col px-4">
          <div className="scrollbar-hide flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center overflow-x-hidden overflow-y-auto py-4">
            <div className="flex w-full flex-col items-center">
              <img
                src={
                  sessionMode === SessionMode.WORKFORCE
                    ? welcomeHeroWorkforce
                    : welcomeHero
                }
                alt=""
                draggable={false}
                className="pointer-events-none mb-1 h-auto w-[min(100%,380px)] max-h-[148px] select-none object-contain"
              />
              {boundAssistant && (
                <span className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-ds-bg-neutral-subtle-default px-3 py-1 text-xs font-medium text-ds-text-neutral-muted-default">
                  <Sparkles className="h-3.5 w-3.5" />
                  办公助手已就绪
                </span>
              )}
              <h1 className="mb-5 w-full text-center text-[22px] font-bold leading-snug text-ds-text-neutral-default-default">
                {title}
              </h1>
              {boundAssistant && skillIds.length > 0 && (
                <div className="-mt-3 mb-4 flex max-w-full flex-wrap justify-center gap-1.5 px-2">
                  {skillIds.map((sid) => (
                    <span
                      key={sid}
                      className="max-w-[10rem] truncate rounded-md bg-ds-bg-neutral-subtle-default px-2 py-0.5 font-mono text-[11px] text-ds-text-neutral-muted-default"
                      title={sid}
                    >
                      {sid}
                    </span>
                  ))}
                </div>
              )}
              {boundAssistant && assistantPrompts.length > 0 && (
                <div className="-mt-1 mb-4 flex w-full flex-col gap-1.5">
                  {assistantPrompts.slice(0, 3).map((p) => (
                    <button
                      key={p}
                      type="button"
                      className="rounded-xl bg-ds-bg-neutral-subtle-default px-3 py-2 text-left text-xs text-ds-text-neutral-default-default transition-opacity hover:opacity-80"
                      onClick={() => {
                        window.dispatchEvent(
                          new CustomEvent("my-cowork:composer-fill", {
                            detail: p,
                          }),
                        );
                      }}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              )}
              <div className="w-full">
                <WorkspaceOverlaysBar />
                <ChatBar
                  {...handlers}
                  placeholder={
                    boundAssistant
                      ? `向「${assistantLabel}」描述任务…`
                      : "描述你想完成的事…"
                  }
                  showFooter
                  modeInteractive
                  disabled={runStatus === "running"}
                  stopping={stopping}
                  onStop={() => void stopTask()}
                />
                <OnboardingHint />
              </div>
            </div>
          </div>

          {recentPreview.length > 0 && (
            <div className="w-full shrink-0 pb-5 pt-1">
              <div className="mb-1.5 flex w-full items-center justify-between gap-2 px-1 text-ds-text-neutral-muted-default">
                <h2 className="text-body-sm font-semibold">最近运行</h2>
                <button
                  type="button"
                  className="group/all inline-flex items-center gap-1 text-body-sm font-medium hover:underline"
                  onClick={() => setHubTab("home")}
                >
                  全部
                  <ArrowRight className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover/all:opacity-100" />
                </button>
              </div>
              <div className="flex flex-col">
                {recentPreview.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="flex w-full items-center gap-2 rounded-lg px-1 py-1.5 text-left text-body-sm text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default hover:text-ds-text-neutral-default-default"
                    onClick={() => setActive(s.id)}
                  >
                    {s.status === "done" ? (
                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-ds-icon-status-completed-default" />
                    ) : (
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ds-border-neutral-default-default" />
                    )}
                    <span className="truncate">{s.title}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    );
  }

  return (
    <section className="main relative flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div className="chat-header">
        <div className="tags flex-1" />
        <Button
          size="icon"
          variant={previewOpen ? "secondary" : "ghost"}
          title="预览面板"
          onClick={() => {
            if (previewOpen) {
              setPreviewOpen(false);
              setPreviewStoreOpen(false);
              setSidePanelVisible(true);
            } else {
              openPreviewFoldSide();
              setPreviewStoreOpen(true);
              addChooser();
            }
          }}
        >
          <Eye className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          variant={runStatus === "running" ? "secondary" : "ghost"}
          title="停止任务"
          disabled={stopping || runStatus !== "running"}
          onClick={() => void stopTask()}
          className={runStatus === "running" ? "text-[var(--danger)]" : undefined}
        >
          <Square className="h-4 w-4" />
        </Button>
      </div>

      <div className="messages chat-surface-container" ref={messagesScrollRef} onScroll={handleMessagesScroll}>
        {turns.map((turn, idx) => {
          const isLast = idx === turns.length - 1;
          const streaming = isLast && runStatus === "running";
          const turnArtifacts = collectArtifacts(
            turn.assistants,
            isLast ? pendingArtifacts : [],
          );
          const lastWithContent = [...turn.assistants]
            .reverse()
            .find((m) => !m.confirm && m.content.trim());
          const hasConfirm = turn.assistants.some((m) => m.confirm);
          const hasAnswer = turn.assistants.some(
            (m) => !m.confirm && Boolean(m.content.trim()),
          );
          const hasContent = hasConfirm || hasAnswer;
          return (
            <div key={turn.user.id} className="group chat-surface-fluid flex w-full min-w-0 flex-col gap-1">
              {turn.user.content.trim() ? (
                <UserMessageBubble content={turn.user.content} />
              ) : null}
              {turn.user.content.trim() ? (
                <MessageCopyRow
                  text={turn.user.content}
                  ts={turn.user.createdAt}
                  align="right"
                />
              ) : null}

              {/* Eigent: plan confirm + Worked for … between user query and final answer */}
              {isLast ? (
                <>
                  <PlanTaskBox />
                  <WorkLogAccordion />
                </>
              ) : null}

              {(hasContent || turnArtifacts.length > 0) && (
                <div className="flex w-full min-w-0 flex-col gap-2.5">
                  {hasContent ? (
                    <AssistantTimeline assistants={turn.assistants} streaming={streaming} />
                  ) : null}
                  {turnArtifacts.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {turnArtifacts.map((a) => (
                        <ArtifactChip key={a.path} artifact={a} />
                      ))}
                    </div>
                  )}
                </div>
              )}
              {/* AionUi: the AI copy/time row appears once per turn, withheld while streaming */}
              {hasContent && !streaming && lastWithContent ? (
                <MessageCopyRow
                  text={lastWithContent.content}
                  ts={lastWithContent.createdAt}
                  align="left"
                />
              ) : null}
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {showScrollBottom && (
        <div className="pointer-events-none absolute bottom-[130px] left-1/2 z-[100] -translate-x-1/2">
          <button
            type="button"
            title="回到底部"
            className="pointer-events-auto flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default shadow-lg transition-colors hover:border-ds-border-neutral-default-default hover:bg-ds-bg-neutral-default-hover"
            style={{ lineHeight: 0 }}
            onClick={() => {
              nearBottomRef.current = true;
              setShowScrollBottom(false);
              messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            <ChevronDown className="h-5 w-5 text-ds-text-neutral-muted-default" />
          </button>
        </div>
      )}

      <div className="composer-wrap chat-surface-container">
        <div className="chat-surface-fluid w-full min-w-0">
          <WorkspaceOverlaysBar />
          <ComposerLiveStatus />
          <ChatBar
            {...handlers}
            placeholder={runStatus === "running" ? "任务进行中，完成后可继续追问…" : "继续追问…"}
            showFooter
            modeInteractive={false}
            disabled={runStatus === "running"}
            stopping={stopping}
            onStop={() => void stopTask()}
          />
        </div>
      </div>
    </section>
  );
}
