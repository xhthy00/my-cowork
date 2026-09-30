import { apiFetch as fetch } from "@/api/backend";
/**
 * Adapted from eigent: ChatBox/BottomBox (InputBox + picker overlays + BoxFooter).
 * Layout: [picker panels] → attachments → rich input → [paperclip | hammer | wand | library] … [send]
 *         → footer [mode | ring + model]
 */
import {
  ArrowRight,
  Boxes,
  ChevronDown,
  ChevronUp,
  Gamepad2,
  Hammer,
  Joystick,
  Library,
  Paperclip,
  Sparkles,
  Square,
  WandSparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { trackChatStream, abortChatStream } from "../../api/chatStream";
import { submitHumanReply } from "../../api/humanReply";
import FileTypeIcon from "@/components/files/FileTypeIcon";
import { postSSE, type SSEvent } from "../../api/sse";
import { RichChatInput } from "./RichChatInput";
import {
  ConnectorPickerPanel,
  IndustryToolPickerPanel,
  KnowledgePickerPanel,
  SkillPickerPanel,
  type PickerItem,
} from "./PickerPanel";
import { cn } from "@/lib/utils";
import { getKnowledgeLogo } from "@/lib/knowledgeLogos";
import type { BoundKnowledgeBase } from "@/lib/knowledgeSources";
import {
  formalAnswerFromContent,
  useSessionStore,
  type Message,
} from "../../store/session";
import { getProjectTaskId, rememberProjectTaskId } from "../../store/livePark";
import {
  ensureActiveSession,
  getActiveProjectContext,
  useSessionsStore,
} from "../../store/sessions";
import { useWorkforceStore } from "../../store/workforce";
import { SessionMode } from "../../types/workforce";
import { SessionTaskBudget, PausedTaskBudget } from "./TaskBudget";
import ChatModelSelect from "./ChatModelSelect";
import ContextUsageIndicator from "./ContextUsageIndicator";
import { useModels } from "@/hooks/useModels";
import type { ReasoningSelection } from "@/window";
import {
  capabilityFor,
  runtimeCapability,
  type ModelCatalog,
} from "../../../../electron/model_capabilities";
import { commandSuggestions, parseChatCommand } from "@/lib/chatCommands";
import { resolveContextUsage } from "@/lib/formatTokens";
import { migrateLegacyMemorySetting } from "@/lib/memorySettingsMigration";
import { followupAppTask } from "@/api/industryAI";
import { appSkillIdsInText } from "@/lib/richText";

interface ChatBarProps {
  onEvent: (event: SSEvent, projectId?: string) => void;
  onSend?: (text: string) => void;
  onStop?: () => void;
  stopping?: boolean;
  disabled?: boolean;
  placeholder?: string;
  showFooter?: boolean;
  modeInteractive?: boolean;
}

export interface ChatAttachment {
  filePath: string;
  fileName: string;
}

type PickerPanelKind = "connector" | "skill" | "knowledge" | "industry";

const HISTORY_MAX_TURNS = 12;
const HISTORY_MAX_CHARS = 6000;

/** Prior turns for /api/chat — read before onSend so the new user msg is excluded. */
export function buildChatHistory(
  messages: Message[],
): { role: string; content: string }[] {
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
  onStop,
  stopping = false,
  disabled,
  placeholder = "描述你想完成的事…",
  showFooter = true,
  modeInteractive = true,
}: ChatBarProps) {
  const [input, setInput] = useState("");
  const modelState = useModels();
  const { active: activeModel } = modelState;
  const [catalog, setCatalog] = useState<ModelCatalog>({
    models: [],
    updatedAt: "",
  });
  const [compacting, setCompacting] = useState(false);
  const [compactStatus, setCompactStatus] = useState("");
  const [contextSnapshot, setContextSnapshot] = useState<{
    sessionId: string;
    modelId: string;
    tokens: number;
    limit: number;
    trigger?: number;
    input_budget?: number;
    compacted?: boolean;
  }>();
  const compactAbort = useRef<AbortController | null>(null);
  const [commandsDismissed, setCommandsDismissed] = useState(false);
  const suggestions = commandsDismissed ? [] : commandSuggestions(input);
  useEffect(() => {
    const reload = () => {
      void window.api
        .getModelCatalog?.()
        .then(setCatalog)
        .catch(() => undefined);
    };
    reload();
    return window.api.onModelCatalogChanged?.(reload);
  }, []);
  const [maintenanceBusy, setMaintenanceBusy] = useState(false);
  useEffect(() => {
    void window.api.industryStatus?.().then(status => setMaintenanceBusy(status.busy));
    return window.api.onIndustryStatus?.(status => setMaintenanceBusy(status.busy));
  }, []);
  const [files, setFiles] = useState<ChatAttachment[]>([]);
  const [openPanel, setOpenPanel] = useState<PickerPanelKind | null>(null);
  const [hoveredFilePath, setHoveredFilePath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [replyError, setReplyError] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const sessionMode = useWorkforceStore((s) => s.sessionMode);
  const setSessionMode = useWorkforceStore((s) => s.setSessionMode);
  const activeProject = useSessionsStore((s) =>
    s.sessions.find((p) => p.id === s.activeId),
  );
  const savedReasoning = activeModel
    ? (activeProject?.modelReasoning?.[activeModel.id] ??
      activeModel.reasoning ??
      {})
    : {};
  // Retire hidden legacy toggles. Budget adapters derive their required flags.
  const { enabled: _legacyToggle, ...reasoning } = savedReasoning;
  const [switchNotice, setSwitchNotice] = useState<{
    sessionId: string;
    modelId: string;
  }>();
  const [restoredTask, setRestoredTask] = useState<string>();
  const failedDraft = activeProject?.failedDraft;
  useEffect(() => {
    setReplyError("");
  }, [activeProject?.id]);
  useEffect(() => {
    if (!failedDraft || failedDraft.taskId === restoredTask) return;
    setReplyError(failedDraft.error);
    if (!input && !files.length) {
      setInput(failedDraft.text);
      setFiles(failedDraft.files);
      setRestoredTask(failedDraft.taskId);
    }
  }, [activeProject?.id, failedDraft, restoredTask, input, files.length]);
  let reasoningError = "";
  if (activeModel && catalog.updatedAt) {
    try {
      runtimeCapability({ ...activeModel, reasoning }, catalog);
    } catch (e) {
      reasoningError = e instanceof Error ? e.message : String(e);
    }
  }
  function changeReasoning(value: ReasoningSelection) {
    if (!activeModel) return;
    setReplyError("");
    const id = ensureActiveSession();
    const store = useSessionsStore.getState();
    const session = store.sessions.find((s) => s.id === id);
    store.touchSession(id, {
      modelProfileId: activeModel.id,
      modelReasoning: { ...session?.modelReasoning, [activeModel.id]: value },
    });
  }
  const boundSkills = useMemo(
    () => activeProject?.enabledSkillIds ?? [],
    [activeProject?.enabledSkillIds],
  );
  const boundKnowledge = useMemo(
    () => activeProject?.boundKnowledgeBases ?? [],
    [activeProject?.boundKnowledgeBases],
  );
  const boundAssistantTitle = activeProject?.assistantId
    ? activeProject.assistantName || activeProject.title
    : null;
  const sessionMessages = useSessionStore((s) => s.messages);
  const pendingQuestion = [...sessionMessages]
    .reverse()
    .find((m) => m.humanQuestion?.status === "pending")?.humanQuestion;
  const contextTokens = useSessionStore((s) => s.contextTokens);
  const contextLimit = useSessionStore((s) => s.contextLimit);
  const budgetMaxTokens = useSessionStore((s) => s.budgetMaxTokens);
  const runStatus = useSessionStore((s) => s.runStatus);
  const running = runStatus === "running";
  const contextUsage = useMemo(
    () =>
      resolveContextUsage({
        messages: sessionMessages,
        draft: input,
        contextTokens:
          !running &&
          contextSnapshot &&
          contextSnapshot.sessionId === activeProject?.id &&
          contextSnapshot?.modelId === activeModel?.id
            ? contextSnapshot.tokens
            : contextTokens > 0
              ? contextTokens
              : undefined,
        contextLimit: running
          ? contextLimit
          : ((contextSnapshot?.sessionId === activeProject?.id &&
            contextSnapshot?.modelId === activeModel?.id
              ? contextSnapshot?.limit
              : undefined) ??
            activeModel?.contextWindow ??
            (activeModel
              ? capabilityFor(activeModel, catalog)?.context
              : undefined) ??
            contextLimit),
        budgetMaxTokens,
      }),
    [
      sessionMessages,
      input,
      contextTokens,
      contextLimit,
      budgetMaxTokens,
      contextSnapshot,
      running,
      activeProject?.id,
      activeModel,
      catalog,
    ],
  );

  useEffect(() => {
    const controller = new AbortController();
    if (!running && !compacting && activeProject?.id && activeModel?.id) {
      const sessionId = activeProject.id,
        modelId = activeModel.id;
      void window.api
        .getBackendUrl()
        .then(async (url) => {
          if (!url || controller.signal.aborted) return;
          const query = new URLSearchParams({
            session_id: sessionId,
            model_profile_id: modelId,
          });
          const response = await fetch(`${url}/api/context?${query}`, {
            signal: controller.signal,
          });
          if (response.ok) {
            const data = await response.json();
            if (!controller.signal.aborted && Number.isFinite(data.tokens))
              setContextSnapshot({
                sessionId,
                modelId,
                tokens: data.tokens,
                limit: data.limit,
                trigger: data.trigger,
                input_budget: data.input_budget,
                compacted: data.compacted,
              });
          }
        })
        .catch(() => undefined);
    }
    return () => {
      controller.abort();
    };
  }, [activeProject?.id, activeModel, running, compacting, catalog]);
  useEffect(() => {
    setCompactStatus("");
    return () => {
      compactAbort.current?.abort();
    };
  }, [activeProject?.id, activeModel?.id]);

  async function compactConversation(focus = "", command = false) {
    if (running || compacting || !activeProject?.id) return;
    if (reasoningError || !activeModel) {
      setCompactStatus(reasoningError || "请选择模型");
      return;
    }
    const sessionId = activeProject.id;
    const originalInput = input;
    const controller = new AbortController();
    compactAbort.current = controller;
    setCompacting(true);
    setCompactStatus("正在压缩较早对话…");
    try {
      const url = await window.api.getBackendUrl();
      if (!url) throw new Error("后端未连接");
      const response = await fetch(`${url}/api/context/compact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          model_profile_id: activeModel?.id,
          reasoning,
          focus,
        }),
        signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.detail || "压缩失败，原上下文已保留");
      if (
        controller.signal.aborted ||
        useSessionsStore.getState().activeId !== sessionId
      )
        return;
      setContextSnapshot({
        sessionId,
        modelId: activeModel?.id ?? "",
        tokens: result.tokens,
        limit: result.limit,
      });
      useSessionStore.setState({
        contextTokens: result.tokens,
        contextLimit: result.limit,
      });
      setCompactStatus(
        `压缩完成：${result.before_tokens.toLocaleString()} → ${result.tokens.toLocaleString()} tokens`,
      );
      if (command)
        setInput((current) => (current === originalInput ? "" : current));
    } catch (error) {
      if (
        !controller.signal.aborted &&
        useSessionsStore.getState().activeId === sessionId
      )
        setCompactStatus(error instanceof Error ? error.message : "压缩失败");
    } finally {
      if (compactAbort.current === controller) {
        compactAbort.current = null;
        setCompacting(false);
      }
    }
  }

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
    if (pendingQuestion) focusInputEnd();
  }, [pendingQuestion?.question_id]);

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

  function persistBoundKnowledge(next: BoundKnowledgeBase[]) {
    const id = useSessionsStore.getState().activeId || ensureActiveSession();
    useSessionsStore.getState().touchSession(id, { boundKnowledgeBases: next });
  }

  function toggleKnowledge(item: PickerItem) {
    const key = item.id;
    const exists = boundKnowledge.some((row) => (row.id || row.name) === key);
    persistBoundKnowledge(
      exists
        ? boundKnowledge.filter((row) => (row.id || row.name) !== key)
        : [...boundKnowledge, { id: item.id, name: item.name, source: "ima" }],
    );
  }

  function removeKnowledge(row: BoundKnowledgeBase) {
    const key = row.id || row.name;
    persistBoundKnowledge(
      boundKnowledge.filter((item) => (item.id || item.name) !== key),
    );
  }

  async function handleAddFile() {
    if (disabled || pendingQuestion) return;
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
    if ((!raw && files.length === 0) || isLoading || compacting) return;
    const command = parseChatCommand(raw);
    if (command && !pendingQuestion) {
      if (files.length) {
        setCompactStatus("压缩命令不处理附件，请先移除附件或另行发送");
        return;
      }
      if (running) {
        setCompactStatus("请等待当前任务结束后压缩");
        return;
      }
      await compactConversation(command.argument, true);
      return;
    }

    if (pendingQuestion) {
      if (!raw) return;
      const projectId = useSessionsStore.getState().activeId;
      if (!projectId) return;
      setIsLoading(true);
      setReplyError("");
      try {
        await submitHumanReply(
          projectId,
          pendingQuestion.task_id,
          pendingQuestion.question_id,
          raw,
        );
        setInput("");
        setFiles([]);
      } catch (err) {
        setReplyError(err instanceof Error ? err.message : "回复失败，请重试");
      } finally {
        setIsLoading(false);
      }
      return;
    }

    if (reasoningError) {
      setReplyError(reasoningError);
      return;
    }
    if (!activeModel && modelState.models.profiles.length) {
      setReplyError("原模型已移除，请重新选择模型");
      return;
    }
    if (activeModel) changeReasoning(reasoning);
    const maintenance = await window.api.industryStatus?.();
    if (maintenance?.busy) {
      setMaintenanceBusy(true);
      return;
    }
    const currentProject = getActiveProjectContext().project;
    if (currentProject?.appOrigin) {
      if (files.length) { setReplyError("请返回业务页面选择附件，追问会沿用原任务的数据与工具范围。"); return; }
      setIsLoading(true); setReplyError("");
      try {
        await followupAppTask(currentProject.id, raw);
        setInput("");
      } catch (error) { setReplyError(error instanceof Error ? error.message : "发起失败"); }
      finally { setIsLoading(false); }
      return;
    }
    let text = raw;
    if (files.length) {
      const paths = files.map((f) => f.filePath).join(", ");
      text = text ? `${text}\n\n[附件: ${paths}]` : `[附件: ${paths}]`;
    }
    const enabledMcp = extractMcpNames(text);
    const sentDraft = { text: input, files: [...files] };
    if (activeProject?.id)
      useSessionsStore
        .getState()
        .touchSession(activeProject.id, { failedDraft: undefined });
    setReplyError("");
    setSwitchNotice(undefined);

    setInput("");
    setFiles([]);
    setOpenPanel(null);
    setIsLoading(true);

    const activeId = useSessionsStore.getState().activeId;
    const prior = useSessionStore.getState().messages;
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
      let backendUrl = (await window.api.getBackendUrl())?.trim() || "";
      if (!backendUrl && window.api.restartBackend) {
        try {
          backendUrl = (await window.api.restartBackend())?.trim() || "";
        } catch (err) {
          const detail = err instanceof Error ? err.message : String(err);
          onEvent(
            {
              type: "step.delta",
              payload: {
                delta: `后端启动失败：${detail}`,
              },
            },
            streamProjectId,
          );
          return;
        }
      }
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
      await migrateLegacyMemorySetting(backendUrl);
      const controller = postSSE(
        `${backendUrl}/api/chat`,
        {
          text,
          task_id: taskId,
          session_mode: sessionMode,
          ...(history.length ? { history } : {}),
          ...(enabledMcp.length ? { enabled_mcp: enabledMcp } : {}),
          space_id: space?.id || project?.spaceId || undefined,
          project_id: streamProjectId,
          session_id: streamProjectId,
          model_profile_id: activeModel?.id ?? project?.modelProfileId,
          reasoning: activeModel ? reasoning : undefined,
          task_budget: project?.taskBudget,
          space_root_path: space?.rootPath || undefined,
          workdir_mode: project?.workdirMode || undefined,
          ...(project?.assistantId
            ? { assistant_id: project.assistantId }
            : {}),
          enabled_skill_ids: [...new Set([...(project?.enabledSkillIds || []), ...appSkillIdsInText(text)])],
          ...(project?.boundKnowledgeBases?.length
            ? { knowledge_bases: project.boundKnowledgeBases }
            : {}),
        },
        (ev) => {
          const evTid =
            typeof ev.payload?.task_id === "string" ? ev.payload.task_id : "";
          if (evTid && evTid !== taskId) return;
          const ownsStream =
            !streamProjectId || getProjectTaskId(streamProjectId) === taskId;
          const visible =
            useSessionsStore.getState().activeId === streamProjectId;
          if (ownsStream && visible && ev.type === "context.compaction") {
            setCompactStatus(
              ev.payload.status === "running" ? "正在整理较早对话…" : "",
            );
          }
          if (ownsStream && ev.type === "graph.end") {
            if (visible) setCompactStatus("");
            if (
              ev.payload.error_code === "context_preparation" &&
              streamProjectId
            ) {
              useSessionsStore.getState().touchSession(streamProjectId, {
                failedDraft: {
                  ...sentDraft,
                  taskId,
                  error: String(ev.payload.error || "上下文整理失败，请重试"),
                },
              });
            }
          }
          onEvent(ev, streamProjectId);
        },
        (message) => {
          if (message.includes("HTTP 503")) {
            setInput(current => current || raw);
            setFiles(current => current.length ? current : files);
          }
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
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Escape") {
      setCommandsDismissed(true);
      return;
    }
    if (suggestions.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      return;
    }
    if (
      suggestions.length &&
      (e.key === "Tab" ||
        (e.key === "Enter" && !e.shiftKey && !parseChatCommand(input)))
    ) {
      e.preventDefault();
      setInput(`/${suggestions[0].name} `);
      focusInputEnd();
      return;
    }
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
    <div className="chat-composer relative z-50 flex w-full min-w-0 flex-col rounded-3xl bg-ds-bg-neutral-default-default">
      {compactStatus && (
        <p
          role="status"
          className="px-4 py-2 text-body-xs text-ds-text-neutral-muted-default"
        >
          {compactStatus}
        </p>
      )}

      {suggestions.length > 0 && (
        <div
          role="listbox"
          aria-label="中文命令"
          className="absolute inset-x-0 bottom-full mb-2 rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default p-2 shadow-lg"
        >
          {suggestions.map((command) => (
            <button
              key={command.name}
              role="option"
              aria-selected="true"
              className="w-full rounded-lg p-2 text-left text-body-sm hover:bg-ds-bg-neutral-subtle-default"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                setInput(`/${command.name} `);
                focusInputEnd();
              }}
            >
              <strong>/{command.name}</strong>
              <span className="ml-3 text-ds-text-neutral-muted-default">
                {command.description}
              </span>
            </button>
          ))}
        </div>
      )}
      {openPanel && (
        <div className="pointer-events-auto absolute inset-x-0 bottom-full z-[60] mb-1 flex flex-col gap-1">
          <div ref={panelRef}>
            {openPanel === "connector" ? (
              <ConnectorPickerPanel
                inputValue={input}
                onToggleItem={toggleToken}
              />
            ) : openPanel === "skill" ? (
              <SkillPickerPanel inputValue={input} onToggleItem={toggleToken} />
            ) : openPanel === "industry" ? (
              <IndustryToolPickerPanel onChoose={(appName, title) => {
                insertToken(`请使用「${appName}」的「${title}」工具，`);
                setOpenPanel(null);
              }} />
            ) : (
              <KnowledgePickerPanel
                selected={boundKnowledge}
                onToggleItem={toggleKnowledge}
              />
            )}
          </div>
        </div>
      )}

      {(boundAssistantTitle || boundKnowledge.length > 0) && (
        <div className="mb-2 flex w-full flex-wrap items-center gap-1.5 px-1">
          {boundAssistantTitle && (
            <span className="inline-flex items-center gap-1 rounded-md bg-ds-bg-neutral-subtle-default px-2 py-0.5 text-[11px] font-medium text-ds-text-neutral-default-default">
              <Sparkles className="h-3 w-3 shrink-0" />
              {boundAssistantTitle}
            </span>
          )}
          {boundSkills.map((sid) => (
            <span
              key={sid}
              className="rounded-md bg-ds-bg-neutral-subtle-default px-1.5 py-0.5 font-mono text-[10px] text-ds-text-neutral-muted-default"
              title={`预加载技能：${sid}`}
            >
              {sid}
            </span>
          ))}
          {boundKnowledge.map((row) => (
            <span
              key={row.id || row.name}
              className="inline-flex items-center gap-1 rounded-md bg-ds-bg-neutral-subtle-default px-1.5 py-0.5 text-[11px] font-medium text-ds-text-neutral-default-default"
              title={`已关联知识库：${row.name}。提问时默认检索此库。`}
            >
              <img
                src={getKnowledgeLogo("ima")}
                alt=""
                className="h-3 w-3 object-contain"
              />
              {row.name}
              <button
                type="button"
                className="inline-flex rounded p-0.5 text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-strong-default"
                aria-label={`取消关联 ${row.name}`}
                onClick={() => removeKnowledge(row)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div
        className={cn(
          "chat-composer-input relative flex w-full flex-col items-start rounded-3xl border border-solid border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default p-3 transition-colors",
          (focused || hasContent) &&
            "border-ds-border-information-default-default",
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
            onChange={(next) => {
              setInput(next);
              setCommandsDismissed(false);
            }}
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
        {replyError && (
          <p className="mb-2 text-xs text-[var(--danger)]" role="alert">
            {replyError}
          </p>
        )}
        {failedDraft && failedDraft.taskId !== restoredTask && (
          <button
            type="button"
            className="mb-2 text-body-xs text-ds-text-neutral-muted-default underline"
            onClick={() => {
              setInput((current) =>
                [current, failedDraft.text].filter(Boolean).join("\n\n"),
              );
              setFiles((current) => [
                ...current,
                ...failedDraft.files.filter(
                  (file) => !current.some((f) => f.filePath === file.filePath),
                ),
              ]);
              setRestoredTask(failedDraft.taskId);
            }}
          >
            恢复上次输入
          </button>
        )}

        <div className="flex w-full flex-wrap items-center justify-between gap-y-2">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              title="附件"
              aria-label="添加文件或照片"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-strong-default"
              disabled={disabled || Boolean(pendingQuestion)}
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
              disabled={disabled || Boolean(pendingQuestion)}
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
              disabled={disabled || Boolean(pendingQuestion)}
              onClick={() => togglePanel("skill")}
            >
              <WandSparkles className="h-4 w-4" />
            </button>
            <button
              type="button"
              title="行业工作台工具"
              data-picker-trigger
              aria-label="查看行业工作台工具"
              aria-haspopup="true"
              aria-expanded={openPanel === "industry"}
              className={cn(
                "inline-flex h-8 w-8 items-center justify-center rounded-lg text-ds-text-brand-default-default hover:bg-ds-bg-brand-subtle-default",
                openPanel === "industry" && "bg-ds-bg-brand-subtle-default",
              )}
              disabled={disabled || Boolean(pendingQuestion)}
              onClick={() => togglePanel("industry")}
            >
              <Boxes className="h-4 w-4" />
            </button>
            <button
              type="button"
              title="知识库"
              data-picker-trigger
              aria-label="关联知识库"
              aria-haspopup="true"
              aria-expanded={openPanel === "knowledge"}
              className={cn(
                "inline-flex h-8 w-8 items-center justify-center rounded-lg text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-strong-default",
                (openPanel === "knowledge" || boundKnowledge.length > 0) &&
                  "bg-ds-bg-neutral-strong-default",
              )}
              disabled={disabled || Boolean(pendingQuestion)}
              onClick={() => togglePanel("knowledge")}
            >
              <Library className="h-4 w-4" />
            </button>
          </div>

          {running && onStop && !pendingQuestion ? (
            <button
              type="button"
              title="停止"
              aria-label="停止任务"
              disabled={stopping}
              onClick={() => onStop()}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--danger)] text-white transition-colors disabled:opacity-35"
            >
              <Square className="h-3.5 w-3.5 fill-current" strokeWidth={0} />
            </button>
          ) : (
            <button
              type="button"
              title="发送"
              disabled={!hasContent || disabled || isLoading || (maintenanceBusy && !pendingQuestion)}
              onClick={() => void handleSend()}
              className={cn(
                "chat-send inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white transition-colors disabled:opacity-35",
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
          )}
        </div>
      </div>

      <PausedTaskBudget />
      {maintenanceBusy && !pendingQuestion && <p role="status" className="mt-2 text-xs text-ds-text-neutral-muted-default">应用正在更新，稍后可继续。输入内容会保留。</p>}
      {showFooter && (
        <div className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-1.5">
          <button
            type="button"
            disabled={!modeInteractive}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-2 py-1 font-medium text-ds-text-neutral-default-default",
              modeInteractive &&
                "bg-ds-bg-neutral-default-default hover:bg-ds-bg-neutral-subtle-default",
              !modeInteractive && "pointer-events-none",
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
            <ModeIcon
              className="size-3.5 shrink-0"
              strokeWidth={2}
              aria-hidden
            />
            <span className="text-label-xs">{modeLabel}</span>
            {modeInteractive && (
              <span className="inline-flex flex-col leading-none" aria-hidden>
                <ChevronUp
                  className="-mb-0.5 size-3 opacity-70"
                  strokeWidth={2}
                />
                <ChevronDown className="size-3 opacity-70" strokeWidth={2} />
              </span>
            )}
          </button>

          <div className="ml-auto flex min-w-0 max-w-full items-center gap-1.5">
            <SessionTaskBudget running={running} />
            <ContextUsageIndicator
              used={contextUsage.used}
              limit={contextUsage.limit}
              trigger={
                !running &&
                contextSnapshot?.sessionId === activeProject?.id &&
                contextSnapshot?.modelId === activeModel?.id
                  ? contextSnapshot?.trigger
                  : undefined
              }
              compacted={
                contextSnapshot?.sessionId === activeProject?.id
                  ? contextSnapshot?.compacted
                  : undefined
              }
              busy={running || compacting}
              canCompact={
                !!activeProject?.id && !!activeModel && !reasoningError
              }
              onCompact={() => void compactConversation()}
            />
            <ChatModelSelect
              modelState={modelState}
              catalog={catalog}
              value={reasoning}
              onChange={changeReasoning}
              onModelChange={(modelId) => {
                if (activeProject?.id && sessionMessages.length)
                  setSwitchNotice({ sessionId: activeProject.id, modelId });
              }}
              error={reasoningError}
              running={running}
            />
          </div>
        </div>
      )}
      {switchNotice &&
        switchNotice.sessionId === activeProject?.id &&
        switchNotice.modelId === activeModel?.id && (
          <div
            role="status"
            className="flex items-start gap-2 px-4 pb-2 text-body-xs text-ds-text-neutral-muted-default"
          >
            <div className="min-w-0 flex-1">
              <p>对话中更换模型可能降低性能表现</p>
              {contextSnapshot?.sessionId === switchNotice.sessionId &&
                contextSnapshot.modelId === switchNotice.modelId &&
                contextSnapshot.trigger !== undefined &&
                contextUsage.used >= contextSnapshot.trigger && (
                  <p>发送前将自动整理较早对话</p>
                )}
            </div>
            <button
              type="button"
              aria-label="关闭模型切换提示"
              className="rounded p-0.5 hover:bg-ds-bg-neutral-subtle-default"
              onClick={() => setSwitchNotice(undefined)}
            >
              <X size={12} />
            </button>
          </div>
        )}
    </div>
  );
}
