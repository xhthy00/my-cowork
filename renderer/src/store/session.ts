import { create } from "zustand";

import type { SSEvent } from "../api/sse";
import { usePreviewStore } from "./preview";
import { usePageTabStore } from "./pageTab";
import { applyToProject } from "./livePark";
import { useWorkforceStore } from "./workforce";
import { decodeUnicodeEscapes, fileBasename } from "@/lib/fsPath";
import { isDeliverableOutputPath } from "@/lib/outputFiles";

export interface FileArtifact {
  name: string;
  path: string;
  kind: "pptx" | "docx" | "xlsx" | "pdf" | "file";
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  artifacts?: FileArtifact[];
  /** Epoch ms — powers the AionUi-style hover copy/timestamp row. */
  createdAt?: number;
  /** Inline confirm request — renders as ChatConfirmCard when pending, collapsed record when resolved. */
  confirm?: {
    call_id: string;
    tool: string;
    args: Record<string, unknown>;
    status: "pending" | "allowed" | "denied";
    responded_at?: number;
  };
}

export interface TraceEvent {
  id: string;
  type: string;
  payload: Record<string, unknown>;
}

export interface TraceNode {
  id: string;
  type: "step" | "tool";
  label: string;
  parent?: string;
  data?: Record<string, unknown>;
}

export interface TraceEdge {
  id: string;
  source: string;
  target: string;
}

export interface ConfirmRequest {
  call_id: string;
  tool: string;
  args: Record<string, unknown>;
}

export type RunStatus = "idle" | "running" | "done" | "error";

export interface SessionState {
  messages: Message[];
  trace: TraceEvent[];
  traceNodes: TraceNode[];
  traceEdges: TraceEdge[];
  confirmQueue: ConfirmRequest[];
  /** call_ids already resolved (approve/deny) — avoid recover re-queue after always-allow. */
  settledConfirmIds: string[];
  /** call_ids currently being silent-approved — do not show card / recover. */
  autoApprovingConfirmIds: string[];
  currentStepId: string | null;
  pendingArtifacts: Array<FileArtifact & { call_id: string }>;
  memoryInjectedCount: number;
  /** Eigent-like task timer for "Worked for Xm Ys" */
  runStatus: RunStatus;
  taskStartedAt: number | null;
  taskElapsedMs: number;
  /** Live token budget from SSE ``budget.update`` (tiktoken estimate). */
  budgetTokens: number;
  budgetMaxTokens: number;
  budgetSteps: number;
  /** Token breakdown from budget.update (if the backend provides it). */
  inputTokens: number;
  outputTokens: number;
  /** Model context window size (sent by backend when known). */
  contextLimit: number;
  /** Tools the user chose "always allow" for in this chat session only (not persisted). */
  alwaysAllowTools: string[];
  /** Live agent thinking state — drives ThoughtDisplay component. */
  thinking: {
    subject: string;
    description: string;
    startedAtMs: number;
    agentId?: string;
  } | null;
  addUserMessage: (text: string) => void;
  appendDelta: (delta: string) => void;
  appendStep: (type: string, payload: Record<string, unknown>) => void;
  appendToolResult: (tool: string, result: Record<string, unknown>) => void;
  enqueueConfirm: (request: ConfirmRequest) => void;
  resolveConfirm: (call_id: string, ok?: boolean) => void;
  addAlwaysAllowTool: (tool: string) => void;
  /** Re-queue confirm_request still pending on the backend (queue empty / always-allow miss). */
  recoverPendingConfirms: () => void;
  replaceMessages: (messages: Message[]) => void;
  resetLiveState: () => void;
  /** Optimistic: show WorkLog immediately on send (before SSE graph.start). */
  beginRun: () => void;
  handleEvent: (event: SSEvent, projectId?: string) => void;
}

async function autoApproveConfirm(callId: string): Promise<boolean> {
  try {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) return false;
    const res = await fetch(
      `${backendUrl}/api/tool/confirm/${encodeURIComponent(callId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ok: true }),
      },
    );
    if (!res.ok) return false;
    try {
      const body = (await res.json()) as { resolved?: boolean };
      // Older backends may omit `resolved`; treat missing as success only if 200.
      if (typeof body.resolved === "boolean") return body.resolved;
    } catch {
      // non-JSON body
    }
    return true;
  } catch {
    return false;
  }
}

/** Last confirm_request with no later matching result — still waiting on backend. */
function unresolvedConfirmFromTrace(
  trace: TraceEvent[],
  confirmQueue: ConfirmRequest[],
  settledConfirmIds: string[],
  autoApprovingConfirmIds: string[] = [],
): ConfirmRequest | null {
  const queued = new Set(confirmQueue.map((c) => c.call_id));
  const settled = new Set(settledConfirmIds);
  const approving = new Set(autoApprovingConfirmIds);
  let lastIdx = -1;
  for (let i = 0; i < trace.length; i++) {
    if (trace[i].type === "tool.confirm_request") lastIdx = i;
  }
  if (lastIdx < 0) return null;
  const ev = trace[lastIdx];
  const callId = String(ev.payload.call_id ?? "");
  if (!callId || queued.has(callId) || settled.has(callId) || approving.has(callId)) {
    return null;
  }
  for (let i = lastIdx + 1; i < trace.length; i++) {
    const later = trace[i];
    if (later.type === "graph.end") return null;
    if (later.type === "tool.result") {
      const cid = String(later.payload.call_id ?? "");
      if (!cid || cid === callId) return null;
    }
  }
  return {
    call_id: callId,
    tool: String(ev.payload.tool ?? ""),
    args: (ev.payload.args as Record<string, unknown>) ?? {},
  };
}

function artifactFromPath(path: string): FileArtifact | null {
  // Decode \uXXXX first — never split on `\` inside escapes.
  const line =
    decodeUnicodeEscapes(path)
      .split(/[\r\n]+/)
      .map((l) => l.trim())
      .find(Boolean) ?? "";
  const trimmed = line.replace(/^[`'"\s]+|[`'";,.\s]+$/g, "");
  if (!trimmed) return null;
  // Require a real path (absolute or ~/…) with a filename.
  if (!trimmed.includes("/") && !trimmed.includes("\\") && !trimmed.startsWith("~")) {
    return null;
  }
  const name = fileBasename(trimmed);
  if (!name || name === trimmed) return null;
  const lower = name.toLowerCase();
  let kind: FileArtifact["kind"] = "file";
  if (lower.endsWith(".pptx")) kind = "pptx";
  else if (lower.endsWith(".docx")) kind = "docx";
  else if (lower.endsWith(".xlsx")) kind = "xlsx";
  else if (lower.endsWith(".pdf")) kind = "pdf";
  else if (/\.(png|jpe?g|webp|gif)$/i.test(lower)) kind = "file";
  return { name, path: trimmed, kind };
}

/** Expand a newline-/comma-joined path blob into individual artifacts. */
function artifactsFromPathBlob(raw: string): FileArtifact[] {
  const parts = raw
    .split(/[\r\n]+/)
    .flatMap((line) => line.split(/,\s+(?=\/|[A-Za-z]:\\)/))
    .map((p) => p.trim())
    .filter(Boolean);
  const out: FileArtifact[] = [];
  const seen = new Set<string>();
  for (const part of parts) {
    const art = artifactFromPath(part);
    if (!art || seen.has(art.path)) continue;
    seen.add(art.path);
    out.push(art);
  }
  return out;
}

function artifactFromConfirm(tool: string, args: Record<string, unknown>): FileArtifact | null {
  const t = tool.toLowerCase();
  const isDocGen =
    /(docx|pptx|xlsx|pdf)\.gen/.test(t) || /(docx|pptx|xlsx|pdf)_gen/.test(t);
  const isFsWrite = t === "fs.write" || t.endsWith(".fs.write") || t.includes("fs_write");
  if (!isDocGen && !isFsWrite) {
    return null;
  }
  const path = String(args.out_path ?? args.path ?? "");
  return artifactFromPath(path);
}

function pushPendingArtifact(
  state: SessionState,
  updates: Partial<SessionState>,
  artifact: FileArtifact,
  callId = "",
): void {
  if (!isDeliverableOutputPath(artifact.path)) return;
  const existing = updates.pendingArtifacts ?? state.pendingArtifacts;
  if (existing.some((a) => a.path === artifact.path)) return;
  updates.pendingArtifacts = [...existing, { ...artifact, call_id: callId }];
}

function isConfirmMessage(message: Message | undefined): boolean {
  return Boolean(message?.confirm);
}

function lastContentAssistant(messages: Message[]): Message | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role === "assistant" && !isConfirmMessage(message)) return message;
  }
  return undefined;
}

function flushArtifactsToMessages(
  state: SessionState,
  updates: Partial<SessionState>,
): void {
  const pending = updates.pendingArtifacts ?? state.pendingArtifacts;
  const arts = pending.map(({ call_id: _c, ...a }) => a);
  if (!arts.length) {
    updates.pendingArtifacts = [];
    return;
  }
  const base = updates.messages ?? state.messages;
  const next = base.slice();
  let last = next[next.length - 1];
  // Confirm cards are UI-only — never hang deliverables on them or the
  // chat/side-panel collectors will hide the files behind a permission row.
  if (!last || last.role !== "assistant" || isConfirmMessage(last)) {
    next.push({ id: nextId(), role: "assistant", content: "" });
    last = next[next.length - 1];
  }
  const merged = [...(last.artifacts ?? [])];
  const seen = new Set(merged.map((a) => a.path));
  for (const a of arts) {
    if (seen.has(a.path)) continue;
    seen.add(a.path);
    merged.push(a);
  }
  next[next.length - 1] = { ...last, artifacts: merged };
  updates.messages = next;
  updates.pendingArtifacts = [];
}

let idCounter = 0;

function nextId(): string {
  return `msg-${++idCounter}`;
}

function appendAssistant(messages: Message[], content: string): Message[] {
  if (!content) return messages;
  const next = messages.slice();
  const last = next[next.length - 1];
  if (last && last.role === "assistant" && !isConfirmMessage(last)) {
    next[next.length - 1] = {
      ...last,
      content: last.content ? `${last.content}\n${content}` : content,
    };
    return next;
  }
  return [...next, { id: nextId(), role: "assistant", content }];
}

function appendDeltaText(messages: Message[], delta: string): Message[] {
  if (!delta) return messages;
  const next = messages.slice();
  const last = next[next.length - 1];
  if (last && last.role === "assistant" && !isConfirmMessage(last)) {
    next[next.length - 1] = { ...last, content: last.content + delta };
    return next;
  }
  return [...next, { id: nextId(), role: "assistant", content: delta, createdAt: Date.now() }];
}

function lastMessageText(update: unknown): string {
  if (!update || typeof update !== "object") return "";
  const messages = (update as { messages?: unknown }).messages;
  if (!Array.isArray(messages) || messages.length === 0) return "";
  const last = messages[messages.length - 1] as { content?: unknown };
  return typeof last?.content === "string" ? last.content.trim() : "";
}

/** Drop supervisor routing noise / truncated junk like "68;" */
const WORKFORCE_WORKER_NODES = new Set([
  "developer_agent",
  "browser_agent",
  "document_agent",
  "multi_modal_agent",
  "coordinator",
]);

function isGarbageAssistantText(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (
    /^(FINISH|developer_agent|browser_agent|document_agent|multi_modal_agent|file_worker|doc_worker|web_worker|msg_worker|PARALLEL:.*)$/i.test(
      t,
    )
  ) {
    return true;
  }
  // NL routing chatter the model sometimes emits instead of a bare worker token
  if (
    /\b(developer_agent|browser_agent|document_agent|multi_modal_agent|file_worker|doc_worker|web_worker|msg_worker)\b/i.test(
      t,
    ) &&
    /needs to handle|should handle|will handle|please (use|call|route)|delegat/i.test(t)
  ) {
    return true;
  }
  if (/^PARALLEL:\s*[\w,]+$/i.test(t)) return true;
  // Status-only chatter without a real deliverable
  if (isStatusOnlyChatter(t)) return true;
  // Workforce process meta (Eigent keeps these in work log / side report, not AgentMessageCard)
  if (isWorkforceProcessMeta(t)) return true;
  // Very short non-Chinese tokens are almost never a real answer
  if (t.length <= 6 && !/[\u4e00-\u9fff]/.test(t) && !/[a-zA-Z]{4,}/.test(t)) {
    return true;
  }
  return false;
}

/** Pure progress lines like「PPT 制作中」with no file path / substance. */
function isStatusOnlyChatter(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (/\.(pptx?|docx?|xlsx|pdf)\b/i.test(t) || /~\/|Desktop|桌面|\//.test(t)) {
    return false;
  }
  const lines = t.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return true;
  const statusRe =
    /(请稍候|制作中|生成中|规划任务|这就为您|如果遇到问题|正在为您|稍等|处理中|开始制作|先规划|正在调用工具)/;
  const substanceRe = /(已生成|已保存|完成了|文件路径|如下|总结|内容如下)/;
  if (substanceRe.test(t)) return false;
  return lines.every((l) => l.length < 100 && statusRe.test(l));
}

/** English workforce meta like "Subtask completed. Deliverable:" — not a formal answer. */
export function isWorkforceProcessMeta(text: string): boolean {
  const withoutThink = text
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/<\/?think>/gi, "")
    .trim();
  if (!withoutThink) return true;
  if (/<summary>[\s\S]*?<\/summary>/i.test(withoutThink)) return false;
  const lines = withoutThink.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return true;
  const metaLine =
    /^(subtask\s+completed\.?|all\s+tasks?\s+completed\.?|all\s+done\.?|deliverable\s*:|failed\s*:|finished\s+\w+_agent)\b/i;
  const mostlyMeta = lines.every(
    (l) => metaLine.test(l) || (/^[-*]\s+/.test(l) && /[/\\]/.test(l) && l.length < 200),
  );
  if (mostlyMeta) return true;
  if (metaLine.test(lines[0]) && !/[\u4e00-\u9fff]/.test(withoutThink)) return true;
  return false;
}

/** Prefer <summary> body; drop process-meta leftovers for AgentMessageCard. */
export function formalAnswerFromContent(content: string): string {
  const summary = content.match(/<summary>([\s\S]*?)<\/summary>/i)?.[1]?.trim();
  if (summary) return summary;
  let withoutThink = content.replace(/<think>[\s\S]*?<\/think>/gi, "\n");
  // Drop unclosed trailing think (streaming).
  withoutThink = withoutThink.replace(/<think>[\s\S]*$/i, "\n");
  withoutThink = withoutThink.replace(/<\/?think>/gi, "");
  withoutThink = withoutThink.replace(/正在调用工具[.。…\s]*/g, "").trim();
  withoutThink = stripProcessTail(withoutThink);
  if (!withoutThink || isWorkforceProcessMeta(withoutThink)) return "";
  // Drop leading English meta paragraphs if a Chinese/markdown body follows.
  const chunks = withoutThink.split(/\n{2,}/);
  const kept = chunks.filter((c) => !isWorkforceProcessMeta(c) && !isOfficeProcessChunk(c));
  return kept.join("\n\n").trim();
}

const PROCESS_TAIL_RE =
  /\n(?:Now let me |Let me (?:add|set|close|build|create|set up)|已完成。[^\n]{0,40}Word|交付摘要|文件规格：)/i;

function stripProcessTail(text: string): string {
  const idx = text.search(PROCESS_TAIL_RE);
  if (idx < 0) return text;
  const head = text.slice(0, idx).trim();
  if (/[\u4e00-\u9fff]/.test(head) && head.length >= 8) return head;
  return text;
}

function isOfficeProcessChunk(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (
    /交付摘要|文件规格：|schema 校验|page layout|pageBreakBefore|fldChar/i.test(t) &&
    t.length < 1200
  ) {
    return true;
  }
  return /^(Now let me |Let me (?:add|set|close|build|create|set up)|已完成。[^\n]{0,40}Word)/i.test(
    t,
  );
}

export const useSessionStore = create<SessionState>((set) => ({
  messages: [],
  trace: [],
  traceNodes: [],
  traceEdges: [],
  confirmQueue: [],
  settledConfirmIds: [],
  autoApprovingConfirmIds: [],
  alwaysAllowTools: [],
  currentStepId: null,
  pendingArtifacts: [],
  memoryInjectedCount: 0,
  runStatus: "idle",
  taskStartedAt: null,
  taskElapsedMs: 0,
  budgetTokens: 0,
  budgetMaxTokens: 200_000,
  budgetSteps: 0,
  inputTokens: 0,
  outputTokens: 0,
  contextLimit: 0,
  thinking: null,

  addUserMessage: (text) =>
    set((state) => ({
      messages: [...state.messages, { id: nextId(), role: "user", content: text, createdAt: Date.now() }],
    })),

  appendDelta: (delta) =>
    set((state) => ({
      messages: appendDeltaText(state.messages, delta),
    })),

  appendStep: (type, payload) =>
    set((state) => ({
      trace: [...state.trace, { id: nextId(), type, payload }],
    })),

  appendToolResult: (tool, result) =>
    set((state) => ({
      trace: [...state.trace, { id: nextId(), type: "tool.result", payload: { tool, result } }],
    })),

  enqueueConfirm: (request) =>
    set((state) => {
      const queueHas = state.confirmQueue.some((c) => c.call_id === request.call_id);
      const msgHas = state.messages.some((m) => m.confirm?.call_id === request.call_id);
      return {
        confirmQueue: queueHas ? state.confirmQueue : [...state.confirmQueue, request],
        messages: msgHas
          ? state.messages
          : [
              ...state.messages,
              {
                id: nextId(),
                role: "assistant" as const,
                content: "",
                createdAt: Date.now(),
                confirm: { ...request, status: "pending" as const },
              },
            ],
      };
    }),

  resolveConfirm: (call_id, ok = true) =>
    set((state) => ({
      confirmQueue: state.confirmQueue.filter((r) => r.call_id !== call_id),
      autoApprovingConfirmIds: state.autoApprovingConfirmIds.filter((id) => id !== call_id),
      settledConfirmIds: state.settledConfirmIds.includes(call_id)
        ? state.settledConfirmIds
        : [...state.settledConfirmIds, call_id],
      pendingArtifacts: ok
        ? state.pendingArtifacts
        : state.pendingArtifacts.filter((a) => a.call_id !== call_id),
      messages: state.messages.map((m) =>
        m.confirm?.call_id === call_id
          ? { ...m, confirm: { ...m.confirm, status: ok ? ("allowed" as const) : ("denied" as const), responded_at: Date.now() } }
          : m,
      ),
    })),

  addAlwaysAllowTool: (tool) =>
    set((state) => {
      const name = tool.trim();
      if (!name || state.alwaysAllowTools.includes(name)) return state;
      return { alwaysAllowTools: [...state.alwaysAllowTools, name] };
    }),

  recoverPendingConfirms: () =>
    set((state) => {
      if (state.runStatus !== "running") return state;
      const missing = unresolvedConfirmFromTrace(
        state.trace,
        state.confirmQueue,
        state.settledConfirmIds,
        state.autoApprovingConfirmIds,
      );
      if (!missing) return state;
      const msgHas = state.messages.some((m) => m.confirm?.call_id === missing.call_id);
      return {
        confirmQueue: [...state.confirmQueue, missing],
        messages: msgHas
          ? state.messages
          : [
              ...state.messages,
              {
                id: nextId(),
                role: "assistant" as const,
                content: "",
                createdAt: Date.now(),
                confirm: { ...missing, status: "pending" as const },
              },
            ],
      };
    }),

  replaceMessages: (messages) => set({ messages }),

  resetLiveState: () =>
    set({
      trace: [],
      traceNodes: [],
      traceEdges: [],
      confirmQueue: [],
      settledConfirmIds: [],
      autoApprovingConfirmIds: [],
      alwaysAllowTools: [],
      currentStepId: null,
      pendingArtifacts: [],
      memoryInjectedCount: 0,
      runStatus: "idle",
      taskStartedAt: null,
      taskElapsedMs: 0,
      budgetTokens: 0,
      budgetMaxTokens: 200_000,
      budgetSteps: 0,
      inputTokens: 0,
      outputTokens: 0,
      contextLimit: 0,
      thinking: null,
    }),

  beginRun: () =>
    set((state) => {
      if (state.runStatus === "running" && state.taskStartedAt) return state;
      return {
        runStatus: "running",
        taskStartedAt: Date.now(),
        taskElapsedMs: 0,
        budgetTokens: 0,
        budgetMaxTokens: state.budgetMaxTokens || 200_000,
        budgetSteps: 0,
        inputTokens: 0,
        outputTokens: 0,
        contextLimit: 0,
        thinking: { subject: "开始分析任务", description: "", startedAtMs: Date.now() },
        confirmQueue: [],
        settledConfirmIds: [],
        autoApprovingConfirmIds: [],
        // Keep alwaysAllowTools for this chat session across turns.
        pendingArtifacts: [],
        currentStepId: null,
        // Keep prior messages; clear live trace for the new turn.
        trace: [],
        traceNodes: [],
        traceEdges: [],
      };
    }),

  handleEvent: (event, projectId) => {
    const payload = event.payload ?? {};

    if (event.type === "graph.start") {
      // Keep seeded Progress plan; only clear agent roster / running slots.
      const plan = useWorkforceStore
        .getState()
        .taskInfo.filter((t) => t.id.startsWith("todo_"));
      useWorkforceStore.getState().reset();
      if (plan.length) useWorkforceStore.getState().seedPlan(plan);
      usePreviewStore.getState().reset();
    }
    if (
      event.type.startsWith("agent.") ||
      event.type === "todo_state" ||
      event.type === "to_sub_tasks" ||
      event.type === "assign_task" ||
      event.type === "task_state" ||
      event.type === "decompose_text"
    ) {
      useWorkforceStore.getState().handleWorkforceEvent(event.type, payload);
    }
    if (event.type === "preview.open" || event.type === "artifact.screenshot") {
      usePreviewStore.getState().handlePreviewEvent(event.type, payload);
    }
    if (event.type === "artifact.file") {
      const art = artifactFromPath(String(payload.path ?? ""));
      if (art) {
        set((state) => {
          const updates: Partial<SessionState> = {};
          pushPendingArtifact(state, updates, art);
          return { ...state, ...updates };
        });
        if (/\.md$/i.test(art.name || art.path)) {
          usePageTabStore.getState().openPreviewFoldSide();
          usePreviewStore.getState().openFile(art.path, art.name);
        }
      }
    }
    // artifact.cleanup: disk cleanup only — keep Trace, do not touch UI artifacts.

    set((state) => {
      // New task → reset live Trace so the panel matches the current run.
      // Do not append status noise into the chat transcript (Eigent keeps that in WorkLog).
      if (event.type === "graph.start") {
        return {
          ...state,
          trace: [{ id: nextId(), type: event.type, payload }],
          traceNodes: [],
          traceEdges: [],
          confirmQueue: [],
          settledConfirmIds: [],
          autoApprovingConfirmIds: [],
          currentStepId: null,
          pendingArtifacts: [],
          memoryInjectedCount: 0,
          runStatus: "running",
          // Preserve optimistic beginRun clock so elapsed doesn't jump back to 0.
          taskStartedAt: state.taskStartedAt ?? Date.now(),
          taskElapsedMs: state.taskStartedAt ? state.taskElapsedMs : 0,
          budgetTokens: 0,
          budgetMaxTokens: state.budgetMaxTokens || 200_000,
          budgetSteps: 0,
          inputTokens: 0,
          outputTokens: 0,
          contextLimit: state.contextLimit,
          thinking: { subject: "开始分析任务", description: "", startedAtMs: Date.now() },
        };
      }

      const trace = [...state.trace, { id: nextId(), type: event.type, payload }];
      const updates: Partial<SessionState> = { trace };

      if (event.type === "budget.update" || event.type === "budget.exhausted") {
        updates.budgetTokens = Number(payload.tokens ?? state.budgetTokens);
        updates.budgetMaxTokens = Number(
          payload.max_tokens ?? state.budgetMaxTokens,
        );
        if (payload.steps != null) {
          updates.budgetSteps = Number(payload.steps);
        }
        if (payload.input_tokens != null) {
          updates.inputTokens = Number(payload.input_tokens);
        }
        if (payload.output_tokens != null) {
          updates.outputTokens = Number(payload.output_tokens);
        }
        if (payload.context_limit != null) {
          updates.contextLimit = Number(payload.context_limit);
        }
      } else if (event.type === "memory.injected") {
        updates.memoryInjectedCount = Number(payload.count ?? 0);
      } else if (event.type === "tool.confirm_request") {
        const tool = String(payload.tool ?? "");
        const args = (payload.args as Record<string, unknown>) ?? {};
        const callId = String(payload.call_id ?? "");
        const request = { call_id: callId, tool, args };
        if (callId) {
          if (tool && state.alwaysAllowTools.includes(tool)) {
            // Silent approve: do not enqueue (avoids card flash). Only show UI if POST fails.
            const approving = state.autoApprovingConfirmIds.includes(callId)
              ? state.autoApprovingConfirmIds
              : [...state.autoApprovingConfirmIds, callId];
            updates.autoApprovingConfirmIds = approving;
            void autoApproveConfirm(callId).then((ok) => {
              const finish = () => {
                const s = useSessionStore.getState();
                if (ok) {
                  s.resolveConfirm(callId, true);
                  return;
                }
                s.enqueueConfirm(request);
                useSessionStore.setState({
                  autoApprovingConfirmIds: useSessionStore
                    .getState()
                    .autoApprovingConfirmIds.filter((id) => id !== callId),
                });
              };
              if (projectId) applyToProject(projectId, finish);
              else finish();
            });
          } else {
            const already = state.confirmQueue.some((c) => c.call_id === callId);
            if (!already) {
              updates.confirmQueue = [...state.confirmQueue, request];
            }
            // Add an inline confirm message so the card appears in the chat timeline.
            const msgAlready = (updates.messages ?? state.messages).some(
              (m) => m.confirm?.call_id === callId,
            );
            if (!msgAlready) {
              updates.messages = [
                ...(updates.messages ?? state.messages),
                {
                  id: nextId(),
                  role: "assistant" as const,
                  content: "",
                  createdAt: Date.now(),
                  confirm: { call_id: callId, tool, args, status: "pending" as const },
                },
              ];
            }
          }
        }
        // NOTE: Do NOT create artifacts from the confirm request — the tool
        // has not run yet. Artifacts are collected from tool.result and
        // artifact.file events only, after the tool actually produces output.
        const stepId = callId || nextId();
        updates.traceNodes = [
          ...state.traceNodes,
          {
            id: stepId,
            type: "tool",
            label: `confirm · ${tool || "tool"}`,
            parent: state.currentStepId ?? undefined,
            data: payload,
          },
        ];
        if (state.currentStepId) {
          updates.traceEdges = [
            ...state.traceEdges,
            {
              id: `${state.currentStepId}->${stepId}`,
              source: state.currentStepId,
              target: stepId,
            },
          ];
        }
      } else if (event.type === "graph.step" || event.type === "step.start") {
        const stepId = String(payload.id ?? nextId());
        const node = String(payload.node ?? "step");
        updates.currentStepId = stepId;
        updates.traceNodes = [
          ...state.traceNodes,
          { id: stepId, type: "step", label: node, data: payload },
        ];
        if (state.currentStepId) {
          updates.traceEdges = [
            ...(updates.traceEdges ?? state.traceEdges),
            {
              id: `${state.currentStepId}->${stepId}`,
              source: state.currentStepId,
              target: stepId,
            },
          ];
        }
        // Worker narrative: workforce intermediate stays in WorkLog (Eigent);
        // only single-agent / non-worker nodes stream into the formal answer.
        // Skip if step.delta already filled the assistant bubble.
        const text = lastMessageText(payload.update);
        const msgsNow = updates.messages ?? state.messages;
        const lastAsst = lastContentAssistant(msgsNow);
        const alreadyStreamed =
          Boolean(lastAsst?.content) &&
          text.length > 0 &&
          lastAsst!.content.includes(text.slice(0, Math.min(48, text.length)));
        if (
          text &&
          !alreadyStreamed &&
          node !== "supervisor" &&
          !WORKFORCE_WORKER_NODES.has(node) &&
          !isGarbageAssistantText(text)
        ) {
          updates.messages = appendAssistant(msgsNow, text);
        }
      } else if (event.type === "step.delta") {
        const delta = String(payload.delta ?? "");
        // Token chunks must not go through isGarbageAssistantText (filters short tokens).
        if (delta) {
          updates.messages = appendDeltaText(state.messages, delta);
        }
      } else if (event.type === "graph.end") {
        const started = state.taskStartedAt;
        const elapsed =
          (started ? Date.now() - started : 0) + state.taskElapsedMs;
        updates.taskStartedAt = null;
        updates.taskElapsedMs = elapsed;
        const endSummary = String(payload.summary ?? "").trim();
        const msgs = updates.messages ?? state.messages;
        const lastAssistant = lastContentAssistant(msgs);
        const alreadyStreamed = Boolean(
          lastAssistant && formalAnswerFromContent(lastAssistant.content).trim(),
        );
        if (
          endSummary &&
          !isGarbageAssistantText(endSummary) &&
          !alreadyStreamed
        ) {
          // Eigent AgentStep.END: one formal answer bubble when nothing streamed yet.
          updates.messages = appendAssistant(msgs, endSummary);
        } else if (
          endSummary &&
          !isGarbageAssistantText(endSummary) &&
          alreadyStreamed &&
          lastAssistant &&
          !formalAnswerFromContent(lastAssistant.content).includes(endSummary.slice(0, 80))
        ) {
          // Streamed body exists but summary adds new substance — append once.
          updates.messages = appendAssistant(msgs, endSummary);
        }
        if (payload.status === "cancelled") {
          updates.runStatus = "done";
          flushArtifactsToMessages(
            { ...state, messages: updates.messages ?? state.messages },
            updates,
          );
          if (
            !(updates.messages ?? state.messages).some(
              (m) => m.role === "assistant" && m.content.trim(),
            )
          ) {
            updates.messages = appendAssistant(
              updates.messages ?? state.messages,
              "任务已停止。",
            );
          }
        } else if (payload.status === "error") {
          updates.runStatus = "error";
          flushArtifactsToMessages(
            { ...state, messages: updates.messages ?? state.messages },
            updates,
          );
          updates.messages = appendAssistant(
            updates.messages ?? state.messages,
            `任务失败：${String(payload.error ?? "未知错误")}`,
          );
        } else if (payload.status === "ok") {
          updates.runStatus = "done";
          flushArtifactsToMessages(
            { ...state, messages: updates.messages ?? state.messages },
            updates,
          );
        }
      } else if (event.type === "tool.result") {
        const parentId = state.currentStepId ?? String(payload.parent ?? "");
        const toolId = String(payload.id ?? nextId());
        updates.traceNodes = [
          ...state.traceNodes,
          {
            id: toolId,
            type: "tool",
            label: String(payload.tool ?? "tool"),
            parent: parentId,
            data: payload,
          },
        ];
        if (parentId) {
          updates.traceEdges = [
            ...state.traceEdges,
            { id: `${parentId}->${toolId}`, source: parentId, target: toolId },
          ];
        }
        const resultPath = String(
          (payload as { path?: string; out_path?: string }).path ??
            (payload as { out_path?: string }).out_path ??
            (payload.result as { path?: string; out_path?: string } | undefined)?.path ??
            (payload.result as { out_path?: string } | undefined)?.out_path ??
            "",
        );
        for (const art of artifactsFromPathBlob(resultPath)) {
          pushPendingArtifact(state, updates, art);
        }
        const resultText = String(
          (payload as { output?: string }).output ??
            (payload.result as { output?: string } | undefined)?.output ??
            payload.result ??
            "",
        );
        const wrote = /Wrote\s+\d+\s+characters\s+to\s+([^\r\n]+)/i.exec(resultText);
        if (wrote?.[1]) {
          for (const art of artifactsFromPathBlob(wrote[1])) {
            pushPendingArtifact(state, updates, art);
          }
        }
      }

      // Thinking state — independent of the else-if chain above.
      if (event.type === "agent.activate" || event.type === "agent.assign" || event.type === "assign_task") {
        const agentId = String(payload.agent_id ?? "");
        const content = String(payload.content ?? "");
        updates.thinking = {
          subject: content || `运行中 · ${agentId}`,
          description: "",
          startedAtMs: state.thinking?.startedAtMs ?? Date.now(),
          agentId,
        };
      } else if (event.type === "agent.deactivate") {
        updates.thinking = state.thinking
          ? { ...state.thinking, subject: `已完成 · ${String(payload.agent_id ?? "")}` }
          : null;
      } else if (event.type === "tool.start") {
        const tool = String(payload.tool ?? "工具");
        const preview = String(payload.preview ?? "").trim();
        updates.thinking = {
          subject: preview ? `正在执行 · ${tool} · ${preview}` : `正在执行 · ${tool}`,
          description: "",
          startedAtMs: state.thinking?.startedAtMs ?? Date.now(),
          agentId: state.thinking?.agentId ?? String(payload.agent_id ?? ""),
        };
      } else if (event.type === "step.delta") {
        const delta = String(payload.delta ?? "");
        if (delta && state.thinking) {
          updates.thinking = { ...state.thinking, subject: "正在生成回答" };
        }
      } else if (event.type === "graph.end") {
        updates.thinking = null;
      }

      return updates;
    });
  },
}));
