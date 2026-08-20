/**
 * Adapted from eigent: ChatBox/BottomBox (InputBox + picker overlays + BoxFooter).
 * Layout: [picker panels] → attachments → rich input → [paperclip | hammer | wand] … [send]
 *         → footer [mode | model]
 */
import {
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Gamepad2,
  Hammer,
  Joystick,
  Paperclip,
  Sparkles,
  WandSparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { trackChatStream, abortChatStream } from "../../api/chatStream";
import FileTypeIcon from "@/components/files/FileTypeIcon";
import { postSSE, type SSEvent } from "../../api/sse";
import { isMemoryEnabled } from "../memory/MemoryView";
import { RichChatInput } from "./RichChatInput";
import {
  ConnectorPickerPanel,
  SkillPickerPanel,
  type PickerItem,
} from "./PickerPanel";
import { cn } from "@/lib/utils";
import { formalAnswerFromContent, useSessionStore, type Message } from "../../store/session";
import {
  getProjectTaskId,
  rememberProjectTaskId,
} from "../../store/livePark";
import { liveBoundId, getActiveProjectContext, useSessionsStore } from "../../store/sessions";
import { useWorkforceStore } from "../../store/workforce";
import { SessionMode } from "../../types/workforce";
import ChatModelSelect from "./ChatModelSelect";

interface ChatBarProps {
  onEvent: (event: SSEvent, projectId?: string) => void;
  onSend?: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  showFooter?: boolean;
  modeInteractive?: boolean;
}

export interface ChatAttachment {
  filePath: string;
  fileName: string;
}

type PickerPanelKind = "connector" | "skill";

const HISTORY_MAX_TURNS = 12;
const HISTORY_MAX_CHARS = 6000;

/** Prior turns for /api/chat — read before onSend so the new user msg is excluded. */
export function buildChatHistory(messages: Message[]): { role: string; content: string }[] {
  return messages
    .slice(-HISTORY_MAX_TURNS)
    .map((m) => {
      let content = (m.content || "").trim();
      if (m.role === "assistant") {
        content = formalAnswerFromContent(content);
      }
      if (m.artifacts?.length) {
        const files = m.artifacts
          .map((a) => a.path || a.name)
          .filter(Boolean)
          .join(", ");
        if (files) content = `${content}\n\n[已生成文件: ${files}]`.trim();
      }
      if (content.length > HISTORY_MAX_CHARS) {
        content = `${content.slice(0, HISTORY_MAX_CHARS)}…`;
      }
      return { role: m.role, content };
    })
    .filter((m) => m.content && (m.role === "user" || m.role === "assistant"));
}

function extractMcpNames(text: string): string[] {
  const names: string[] = [];
  for (const m of text.matchAll(/@([A-Za-z0-9_-]+)/g)) {
    if (m[1] && !names.includes(m[1])) names.push(m[1]);
  }
  return names;
}

export default function ChatBar({
  onEvent,
  onSend,
  disabled,
  placeholder = "描述你想完成的事…",
  showFooter = true,
  modeInteractive = true,
}: ChatBarProps) {
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<ChatAttachment[]>([]);
  const [openPanel, setOpenPanel] = useState<PickerPanelKind | null>(null);
  const [hoveredFilePath, setHoveredFilePath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const sessionMode = useWorkforceStore((s) => s.sessionMode);
  const setSessionMode = useWorkforceStore((s) => s.setSessionMode);
  const activeProject = useSessionsStore((s) =>
    s.sessions.find((p) => p.id === s.activeId),
  );
  const boundSkills = useMemo(
    () => activeProject?.enabledSkillIds ?? [],
    [activeProject?.enabledSkillIds],
  );
  const boundAssistantTitle = activeProject?.assistantId
    ? activeProject.assistantName || activeProject.title
    : null;

  useEffect(() => {
    const onFill = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (typeof detail === "string") {
        setInput(detail);
        focusInputEnd();
      }
    };
    window.addEventListener("my-cowork:composer-fill", onFill);
    return () => window.removeEventListener("my-cowork:composer-fill", onFill);
  }, []);

  useEffect(() => {
    if (!openPanel) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        panelRef.current?.contains(target ?? null) ||
        target?.closest("[data-picker-trigger]")
      ) {
        return;
      }
      setOpenPanel(null);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [openPanel]);

  function focusInputEnd() {
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
    });
  }

  function insertToken(token: string) {
    setInput((prev) => {
      const trimmed = prev.replace(/\s+$/, "");
      return (trimmed.length ? `${trimmed} ` : "") + `${token} `;
    });
    focusInputEnd();
  }

  function removeToken(token: string) {
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    setInput((prev) =>
      prev
        .replace(new RegExp(`\\s?${escaped}`), "")
        .replace(/\s{2,}/g, " ")
        .replace(/^\s+/, ""),
    );
    focusInputEnd();
  }

  function toggleToken(item: PickerItem) {
    if (input.includes(item.token)) removeToken(item.token);
    else insertToken(item.token);
  }

  function togglePanel(panel: PickerPanelKind) {
    setOpenPanel((prev) => (prev === panel ? null : panel));
  }

  async function handleAddFile() {
    if (disabled) return;
    try {
      if (!window.api?.selectFile) {
        window.alert("请使用桌面客户端选择附件（需完整绝对路径）。");
        return;
      }
      const result = await window.api.selectFile({ title: "选择文件" });
      if (!result?.success || !result.files?.length) return;
      const absolute = result.files.filter(
        (f) =>
          typeof f.filePath === "string" &&
          (f.filePath.startsWith("/") || /^[A-Za-z]:[\\/]/.test(f.filePath)),
      );
      if (!absolute.length) {
        window.alert("未能获取文件绝对路径，请重试选择附件。");
        return;
      }
      setFiles((prev) => {
        const next = [...prev];
        for (const f of absolute) {
          if (!next.some((x) => x.filePath === f.filePath)) next.push(f);
        }
        return next;
      });
    } catch (err) {
      console.error("Select File Error:", err);
    }
  }

  function handleRemoveFile(filePath: string) {
    setFiles((prev) => prev.filter((f) => f.filePath !== filePath));
  }

  async function handleSend() {
    const raw = input.trim();
    if ((!raw && files.length === 0) || isLoading) return;

    let text = raw;
    if (files.length) {
      const paths = files.map((f) => f.filePath).join(", ");
      text = text
        ? `${text}\n\n[附件: ${paths}]`
        : `[附件: ${paths}]`;
    }
    const enabledMcp = extractMcpNames(text);

    setInput("");
    setFiles([]);
    setOpenPanel(null);
    setIsLoading(true);

    const activeId = useSessionsStore.getState().activeId;
    const prior =
      activeId && liveBoundId === activeId
        ? useSessionsStore.getState().getMessages(activeId)
        : useSessionStore.getState().messages;
    const history = buildChatHistory(prior);
    const { project, space } = getActiveProjectContext();
    const streamProjectId = project?.id || activeId || undefined;
    const taskId =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `task-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    if (streamProjectId) {
      const prevTask = getProjectTaskId(streamProjectId);
      if (prevTask) abortChatStream(prevTask);
      rememberProjectTaskId(streamProjectId, taskId);
    }
    onSend?.(text);

    try {
      const backendUrl = await window.api.getBackendUrl();
      if (!backendUrl) {
        onEvent(
          {
            type: "step.delta",
            payload: {
              delta:
                "后端未连接。请先打开设置保存 API Key（保存后会自动启动后端），再重新发送。",
            },
          },
          streamProjectId,
        );
        return;
      }
      const controller = postSSE(
        `${backendUrl}/api/chat`,
        {
          text,
          task_id: taskId,
          session_mode: sessionMode,
          memory_enabled: isMemoryEnabled(),
          ...(history.length ? { history } : {}),
          ...(enabledMcp.length ? { enabled_mcp: enabledMcp } : {}),
          space_id: space?.id || project?.spaceId || undefined,
          project_id: streamProjectId,
          session_id: streamProjectId,
          space_root_path: space?.rootPath || undefined,
          workdir_mode: project?.workdirMode || undefined,
          ...(project?.assistantId
            ? { assistant_id: project.assistantId }
            : {}),
          ...(project?.enabledSkillIds?.length
            ? { enabled_skill_ids: project.enabledSkillIds }
            : {}),
        },
        (ev) => onEvent(ev, streamProjectId),
        (message) => {
          onEvent(
            { type: "step.delta", payload: { delta: message } },
            streamProjectId,
          );
        },
      );
      trackChatStream(taskId, controller);
    } catch {
      onEvent(
        {
          type: "step.delta",
          payload: { delta: "发送失败：无法连接后端，请检查 API Key 后重试。" },
        },
        streamProjectId,
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void handleSend();
    }
  }

  const hasContent = input.trim().length > 0 || files.length > 0;
  const isSingle = sessionMode === SessionMode.SINGLE_AGENT;
  const modeLabel = isSingle ? "单智能体" : "多智能体";
  const ModeIcon = isSingle ? Joystick : Gamepad2;
  const visibleFiles = files.slice(0, 5);
  const remainingCount = files.length > 5 ? files.length - 5 : 0;

  return (
    <div className="relative z-50 flex w-full min-w-0 flex-col rounded-3xl bg-ds-bg-neutral-default-default">
      {openPanel && (
        <div className="pointer-events-auto absolute inset-x-0 bottom-full z-[60] mb-1 flex flex-col gap-1">
          <div ref={panelRef}>
            {openPanel === "connector" ? (
              <ConnectorPickerPanel
                inputValue={input}
                onToggleItem={toggleToken}
              />
            ) : (
              <SkillPickerPanel inputValue={input} onToggleItem={toggleToken} />
            )}
          </div>
        </div>
      )}

      {boundAssistantTitle && (
        <div className="mb-2 flex w-full flex-wrap items-center gap-1.5 px-1">
          <span className="inline-flex items-center gap-1 rounded-md bg-ds-bg-neutral-subtle-default px-2 py-0.5 text-[11px] font-medium text-ds-text-neutral-default-default">
            <Sparkles className="h-3 w-3 shrink-0" />
            {boundAssistantTitle}
          </span>
          {boundSkills.map((sid) => (
            <span
              key={sid}
              className="rounded-md bg-ds-bg-neutral-subtle-default px-1.5 py-0.5 font-mono text-[10px] text-ds-text-neutral-muted-default"
              title={`预加载技能：${sid}`}
            >
              {sid}
            </span>
          ))}
        </div>
      )}

      <div
        className={cn(
          "relative flex w-full flex-col items-start rounded-3xl border border-solid border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default p-3 transition-colors",
          (focused || hasContent) && "border-ds-border-information-default-default",
        )}
      >
        {files.length > 0 && (
          <div className="relative box-border flex w-full flex-wrap items-start gap-1 pb-2">
            {visibleFiles.map((file) => {
              const isHovered = hoveredFilePath === file.filePath;
              return (
                <div
                  key={file.filePath}
                  className="relative box-border flex h-auto max-w-24 items-center gap-0.5 rounded-md bg-ds-bg-neutral-default-default pr-1"
                  onMouseEnter={() => setHoveredFilePath(file.filePath)}
                  onMouseLeave={() =>
                    setHoveredFilePath((prev) =>
                      prev === file.filePath ? null : prev,
                    )
                  }
                >
                  <button
                    type="button"
                    className="flex h-6 w-6 items-center justify-center rounded-md"
                    title={isHovered ? "移除文件" : file.fileName}
                    onClick={() => handleRemoveFile(file.filePath)}
                  >
                    {isHovered ? (
                      <X className="size-3.5 text-ds-icon-neutral-muted-default" />
                    ) : (
                      <FileTypeIcon pathOrName={file.fileName} size="sm" />
                    )}
                  </button>
                  <p
                    className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-['Inter'] text-xs font-bold leading-tight text-ds-text-neutral-default-default"
                    title={file.fileName}
                  >
                    {file.fileName}
                  </p>
                </div>
              );
            })}
            {remainingCount > 0 && (
              <span className="rounded-lg bg-ds-bg-neutral-strong-default px-2 py-0.5 text-xs font-bold text-ds-text-neutral-default-default">
                {remainingCount}+
              </span>
            )}
          </div>
        )}

        <div className="relative flex w-full flex-1 items-start justify-center gap-2.5 pb-3">
          <RichChatInput
            ref={inputRef}
            value={input}
            onChange={(next) => setInput(next)}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            disabled={disabled || isLoading}
            placeholder={placeholder}
            className="border-none shadow-none focus-visible:ring-0 max-h-[200px] min-h-[40px]"
            textClassName="text-ds-text-neutral-default-default"
            style={{
              fontFamily: "Inter",
              fontSize: "13px",
              lineHeight: "20px",
            }}
          />
        </div>

        <div className="flex w-full flex-wrap items-center justify-between gap-y-2">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              title="附件"
              aria-label="添加文件或照片"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-strong-default"
              disabled={disabled}
              onClick={() => void handleAddFile()}
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <button
              type="button"
              title="连接器"
              data-picker-trigger
              aria-label="添加连接器"
              aria-haspopup="true"
              aria-expanded={openPanel === "connector"}
              className={cn(
                "inline-flex h-8 w-8 items-center justify-center rounded-lg text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-strong-default",
                openPanel === "connector" && "bg-ds-bg-neutral-strong-default",
              )}
              disabled={disabled}
              onClick={() => togglePanel("connector")}
            >
              <Hammer className="h-4 w-4" />
            </button>
            <button
              type="button"
              title="技能"
              data-picker-trigger
              aria-label="添加技能"
              aria-haspopup="true"
              aria-expanded={openPanel === "skill"}
              className={cn(
                "inline-flex h-8 w-8 items-center justify-center rounded-lg text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-strong-default",
                openPanel === "skill" && "bg-ds-bg-neutral-strong-default",
              )}
              disabled={disabled}
              onClick={() => togglePanel("skill")}
            >
              <WandSparkles className="h-4 w-4" />
            </button>
          </div>

          <button
            type="button"
            title="发送"
            disabled={!hasContent || disabled || isLoading}
            onClick={() => void handleSend()}
            className={cn(
              "inline-flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors disabled:opacity-35",
              hasContent
                ? "bg-[var(--colors-green-default)]"
                : "bg-ds-text-neutral-default-default",
            )}
          >
            <ArrowRight
              className={cn(
                "h-4 w-4 transition-transform duration-200",
                hasContent && "-rotate-90",
              )}
              strokeWidth={2.2}
            />
          </button>
        </div>
      </div>

      {showFooter && (
        <div className="flex w-full items-center justify-between gap-2 px-3 py-1">
          <button
            type="button"
            disabled={!modeInteractive}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-xl bg-ds-bg-neutral-default-default px-2 py-1 text-label-xs font-semibold text-ds-text-neutral-default-default",
              modeInteractive && "hover:bg-ds-bg-neutral-subtle-default",
              !modeInteractive && "pointer-events-none bg-transparent",
            )}
            onClick={() => {
              if (!modeInteractive) return;
              setSessionMode(
                isSingle ? SessionMode.WORKFORCE : SessionMode.SINGLE_AGENT,
              );
            }}
            title="会话模式"
            aria-label={`会话模式: ${modeLabel}`}
          >
            <ModeIcon className="size-3.5 shrink-0" strokeWidth={2} aria-hidden />
            <span>{modeLabel}</span>
            {modeInteractive && (
              <span className="inline-flex flex-col leading-none" aria-hidden>
                <ChevronUp className="-mb-1 size-3 opacity-80" strokeWidth={2} />
                <ChevronDown className="size-3 opacity-80" strokeWidth={2} />
              </span>
            )}
          </button>

          <ChatModelSelect />
        </div>
      )}
    </div>
  );
}
