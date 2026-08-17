import { AlertTriangle, ChevronDown, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { useCallback, useId, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { humanizeTool } from "../../lib/processLabels";
import type { Message } from "../../store/session";
import { useSessionStore } from "../../store/session";
import { cn } from "../../lib/utils";

/** Permission intent classification, ported from AionUi `permissionOptions.ts`. */
type PermissionIntent = "allow-once" | "allow-always" | "reject-once" | "reject-always" | "neutral";

type ConfirmOption = {
  id: string;
  value: "proceed_once" | "proceed_always" | "cancel";
  label: string;
  intent: PermissionIntent;
  testId: string;
  disabled?: boolean;
};

const CONFIRM_OPTIONS: ConfirmOption[] = [
  { id: "proceed_once", value: "proceed_once", label: "本次允许", intent: "allow-once", testId: "message-permission-option-proceed_once" },
  { id: "proceed_always", value: "proceed_always", label: "本会话总是允许此工具", intent: "allow-always", testId: "message-permission-option-proceed_always" },
  { id: "cancel", value: "cancel", label: "拒绝", intent: "reject-once", testId: "message-permission-option-cancel" },
];

type OperationKind = "execute" | "edit" | "read" | "fetch" | "tool";

const OPERATION_LABEL: Record<OperationKind, string> = {
  execute: "执行命令",
  edit: "编辑文件",
  read: "读取文件",
  fetch: "网络访问",
  tool: "工具调用",
};

function getOperationKind(tool: string): OperationKind {
  const key = tool.toLowerCase();
  if (key.includes("bash") || key.includes("exec") || key.includes("terminal")) return "execute";
  if (key.includes("write") || key.includes("edit") || key.includes("patch")) return "edit";
  if (key.includes("read") || key.includes("list") || key.includes("info")) return "read";
  if (key.includes("fetch") || key.includes("web") || key.includes("search") || key.includes("browse")) return "fetch";
  return "tool";
}

function getOperationDescription(tool: string, kind: OperationKind): string | undefined {
  const descriptions: Record<OperationKind, string> = {
    execute: "请求执行 Shell 命令",
    edit: "请求修改文件内容",
    read: "请求读取文件",
    fetch: "请求网络访问",
    tool: "请求调用工具",
  };
  const desc = descriptions[kind];
  return desc ? `${desc} · ${humanizeTool(tool)}` : undefined;
}

function renderDetail(tool: string, args: Record<string, unknown>): string {
  if (tool.includes("bash") || tool.includes("exec")) {
    return `命令: ${String(args.cmd ?? "")}\n工作目录: ${String(args.cwd ?? "")}`;
  }
  if (tool.includes("write") && tool.includes("fs")) {
    const content = String(args.content ?? "");
    const summary = content.length > 800 ? `${content.slice(0, 800)}…` : content;
    return `路径: ${String(args.path ?? "")}\n内容: ${summary}`;
  }
  if (tool.includes("read") && tool.includes("fs")) {
    return `路径: ${String(args.path ?? "")}`;
  }
  if (/(pptx|docx|xlsx|pdf).gen/.test(tool) || /(pptx|docx|xlsx|pdf)_gen/.test(tool)) {
    const lines = [`路径: ${String(args.out_path ?? args.path ?? "")}`];
    if (args.template_id != null) lines.push(`模板: ${String(args.template_id)}`);
    if (Array.isArray(args.slides)) lines.push(`页数: ${args.slides.length}`);
    if (args.outline != null) lines.push("大纲: (json)");
    if (args.sheet != null) lines.push("表格: (json)");
    if (typeof args.html === "string") {
      const html = args.html;
      lines.push(`html: ${html.length > 80 ? `${html.slice(0, 80)}…` : html}`);
    }
    return lines.join("\n");
  }
  return Object.entries(args)
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join("\n");
}

type ConfirmData = NonNullable<Message["confirm"]>;

function OptionSpinner({ active }: { active: boolean }) {
  if (!active) return null;
  return <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />;
}

/**
 * Inline tool-confirm card.
 * Layout: AionUi PermissionRequestPanel (title / badge / command / options).
 * Chrome: Eigent PlanTaskBox (rounded-2xl splitting surface, header, footer CTAs).
 *
 * Single-click submits immediately (no separate confirm step). After the
 * response is sent, resolveConfirm updates the message's confirm.status,
 * and ChatView swaps this card for ChatConfirmRecord.
 */
export default function ChatConfirmCard({ confirm }: { confirm: ConfirmData }) {
  const resolveConfirm = useSessionStore((state) => state.resolveConfirm);
  const addAlwaysAllowTool = useSessionStore((state) => state.addAlwaysAllowTool);

  const [isResponding, setIsResponding] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const optionsLabelId = useId();

  const toolTitle = humanizeTool(confirm.tool);
  const operationKind = getOperationKind(confirm.tool);
  const operationDescription = getOperationDescription(confirm.tool, operationKind);
  const detail = renderDetail(confirm.tool, confirm.args);
  const allowOnce = CONFIRM_OPTIONS[0];
  const allowAlways = CONFIRM_OPTIONS[1];
  const rejectOnce = CONFIRM_OPTIONS[2];

  const submitOption = useCallback(
    async (option: ConfirmOption) => {
      if (isResponding || option.disabled) return;

      const ok = option.intent !== "reject-once";
      setIsResponding(true);
      setSubmittingId(option.id);
      setHasError(false);

      try {
        if (option.value === "proceed_always") {
          addAlwaysAllowTool(confirm.tool);
        }
        const backendUrl = await window.api.getBackendUrl();
        if (backendUrl) {
          await fetch(`${backendUrl}/api/tool/confirm/${encodeURIComponent(confirm.call_id)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ok }),
          });
        }
        resolveConfirm(confirm.call_id, ok);
      } catch {
        setHasError(true);
      } finally {
        setIsResponding(false);
        setSubmittingId(null);
      }
    },
    [confirm, isResponding, resolveConfirm, addAlwaysAllowTool],
  );

  return (
    <div
      className="chat-confirm-card relative mb-3 flex w-full min-w-0 shrink-0 flex-col overflow-hidden rounded-2xl bg-ds-bg-splitting-subtle-default"
      role="region"
      aria-labelledby="chat-confirm-title"
      data-testid="message-permission-card"
    >
      <div className="flex min-w-0 items-center gap-2 border-x-0 border-b border-t-0 border-solid border-ds-border-neutral-subtle-default px-3 py-2">
        <span
          id="chat-confirm-title"
          className="min-w-0 flex-1 truncate text-left text-body-sm font-bold text-ds-text-neutral-default-default"
        >
          {toolTitle}
        </span>
        <span className="inline-flex shrink-0 items-center rounded-full border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default/80 px-1.5 py-px text-[10px] font-medium leading-[1.4] text-ds-text-neutral-muted-default">
          {OPERATION_LABEL[operationKind]}
        </span>
      </div>

      <div className="flex min-w-0 flex-col gap-2.5 px-3 py-2.5" aria-busy={isResponding}>
        {operationDescription && (
          <span className="block [overflow-wrap:anywhere] text-[12px] leading-[1.4] text-ds-text-neutral-muted-default">
            {operationDescription}
          </span>
        )}

        {detail && (
          <div className="confirm-detail-block min-w-0 rounded-[7px] bg-ds-bg-neutral-subtle-default/70 px-2.5 py-[7px]">
            <span className="shrink-0 text-[11px] text-ds-text-neutral-muted-default">命令</span>
            <code
              dir="auto"
              className="min-w-0 flex-1 overflow-auto [overflow-wrap:anywhere] whitespace-pre-wrap bg-transparent font-mono text-[11px] leading-[1.45] text-ds-text-neutral-default-default"
            >
              {detail}
            </code>
          </div>
        )}

        {hasError && (
          <div
            className="flex items-start gap-2 rounded-[9px] border px-2.5 py-2 text-[12px] leading-[1.5]"
            style={{
              color: "var(--danger)",
              background: "var(--danger-soft)",
              borderColor: "var(--danger)",
            }}
            role="alert"
            aria-live="assertive"
            data-testid="message-permission-error"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>响应发送失败</span>
          </div>
        )}
      </div>

      <fieldset className="m-0 min-w-0 border-0 p-0" disabled={isResponding}>
        <legend id={optionsLabelId} className="sr-only">
          选择操作
        </legend>
        {CONFIRM_OPTIONS.length > 0 ? (
          <div
            className="flex flex-wrap items-center justify-end gap-2 px-3 pb-3 pt-1"
            role="group"
            aria-labelledby={optionsLabelId}
            data-testid="message-permission-options"
          >
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={rejectOnce.disabled || isResponding}
              data-disabled={Boolean(rejectOnce.disabled || isResponding)}
              data-testid={rejectOnce.testId}
              onClick={() => void submitOption(rejectOnce)}
              className="!rounded-full !text-ds-text-neutral-muted-default"
            >
              <OptionSpinner active={submittingId === rejectOnce.id} />
              {rejectOnce.label}
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={allowAlways.disabled || isResponding}
              data-disabled={Boolean(allowAlways.disabled || isResponding)}
              data-testid={allowAlways.testId}
              onClick={() => void submitOption(allowAlways)}
              className="!rounded-full"
            >
              <OptionSpinner active={submittingId === allowAlways.id} />
              {allowAlways.label}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={allowOnce.disabled || isResponding}
              data-disabled={Boolean(allowOnce.disabled || isResponding)}
              data-testid={allowOnce.testId}
              onClick={() => void submitOption(allowOnce)}
              className={cn(
                "!rounded-full",
                "!border-[var(--colors-green-default)] !bg-[var(--colors-green-default)] !text-white",
                "hover:!opacity-90",
              )}
            >
              <OptionSpinner active={submittingId === allowOnce.id} />
              {allowOnce.label}
            </Button>
          </div>
        ) : (
          <span className="mx-3 mb-3 block rounded-[9px] border border-dashed border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 py-2.5 text-[12px] text-ds-text-neutral-muted-default">
            没有可用的操作选项
          </span>
        )}
      </fieldset>
    </div>
  );
}

function confirmToneClass(isAllowed: boolean, extra?: string) {
  return cn(
    "w-full shrink-0 min-w-0 rounded-xl border text-[12px] leading-[1.5]",
    isAllowed
      ? "border-[var(--ds-icon-status-completed-default)] bg-[var(--ds-bg-status-completed-subtle-default)]"
      : "border-[var(--danger)] bg-[var(--danger-soft)]",
    extra,
  );
}

function ConfirmRecordHeader({
  confirm,
  trailing,
}: {
  confirm: ConfirmData;
  trailing?: ReactNode;
}) {
  const isAllowed = confirm.status === "allowed";
  const toolTitle = humanizeTool(confirm.tool);
  const operationKind = getOperationKind(confirm.tool);
  const kindLabel = OPERATION_LABEL[operationKind];
  const showKind = kindLabel !== toolTitle;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-1.5">
      {isAllowed ? (
        <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-[var(--ds-icon-status-completed-default)]" />
      ) : (
        <XCircle className="h-3.5 w-3.5 shrink-0 text-[var(--danger)]" />
      )}
      <span
        className="shrink-0 font-medium"
        style={{ color: isAllowed ? "var(--ds-text-status-completed-default)" : "var(--danger)" }}
      >
        {isAllowed ? "已允许" : "已拒绝"}
      </span>
      <span className="shrink-0 text-ds-text-neutral-muted-default">·</span>
      <span className="min-w-0 truncate text-ds-text-neutral-default-default">{toolTitle}</span>
      {showKind ? (
        <>
          <span className="shrink-0 text-ds-text-neutral-muted-default">·</span>
          <span className="shrink-0 text-[10px] text-ds-text-neutral-muted-default">{kindLabel}</span>
        </>
      ) : null}
      {trailing}
    </div>
  );
}

/**
 * Resolved confirm row. Command details stay folded until the user expands.
 */
export function ChatConfirmRecord({
  confirm,
  defaultOpen = false,
  nested = false,
}: {
  confirm: ConfirmData;
  defaultOpen?: boolean;
  nested?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const isAllowed = confirm.status === "allowed";
  const detail = renderDetail(confirm.tool, confirm.args);
  const summary = detail.split("\n")[0].trim();

  return (
    <details
      className={confirmToneClass(isAllowed, nested ? "mb-0 px-2.5 py-1.5" : "mb-3 px-3 py-2")}
      data-testid="message-permission-record"
      open={open}
    >
      <summary
        className="flex cursor-pointer list-none items-center gap-1.5 marker:content-none [&::-webkit-details-marker]:hidden"
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        <ConfirmRecordHeader
          confirm={confirm}
          trailing={
            <ChevronDown
              className={cn(
                "ml-auto h-3.5 w-3.5 shrink-0 text-ds-text-neutral-muted-default transition-transform",
                open && "rotate-180",
              )}
            />
          }
        />
      </summary>
      {summary ? (
        <code
          dir="auto"
          className="mt-1 block min-w-0 whitespace-pre-wrap break-all bg-transparent font-mono text-[11px] text-ds-text-neutral-muted-default"
        >
          {detail}
        </code>
      ) : null}
    </details>
  );
}

/**
 * Consecutive resolved confirms collapse into one row so they don't bury the answer.
 */
export function ChatConfirmRecordGroup({ confirms }: { confirms: ConfirmData[] }) {
  const [open, setOpen] = useState(false);
  if (confirms.length === 1) {
    return <ChatConfirmRecord confirm={confirms[0]} />;
  }

  const allowed = confirms.filter((c) => c.status === "allowed").length;
  const denied = confirms.length - allowed;
  const allAllowed = denied === 0;
  const label =
    denied === 0
      ? `已允许 ${confirms.length} 项操作`
      : allowed === 0
        ? `已拒绝 ${confirms.length} 项操作`
        : `已执行 ${confirms.length} 项操作`;

  return (
    <details
      className={confirmToneClass(allAllowed, "mb-3 px-3 py-2")}
      data-testid="message-permission-record-group"
      open={open}
    >
      <summary
        className="flex cursor-pointer list-none items-center gap-1.5 marker:content-none [&::-webkit-details-marker]:hidden"
        onClick={(event) => {
          event.preventDefault();
          setOpen((value) => !value);
        }}
      >
        {allAllowed ? (
          <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-[var(--ds-icon-status-completed-default)]" />
        ) : (
          <XCircle className="h-3.5 w-3.5 shrink-0 text-[var(--danger)]" />
        )}
        <span
          className="min-w-0 truncate font-medium"
          style={{ color: allAllowed ? "var(--ds-text-status-completed-default)" : "var(--danger)" }}
        >
          {label}
        </span>
        {denied > 0 && allowed > 0 ? (
          <span className="shrink-0 text-[11px] text-ds-text-neutral-muted-default">
            允许 {allowed} · 拒绝 {denied}
          </span>
        ) : null}
        <ChevronDown
          className={cn(
            "ml-auto h-3.5 w-3.5 shrink-0 text-ds-text-neutral-muted-default transition-transform",
            open && "rotate-180",
          )}
        />
      </summary>
      <div className="mt-2 flex flex-col gap-1.5">
        {confirms.map((confirm) => (
          <ChatConfirmRecord
            key={confirm.call_id}
            confirm={confirm}
            defaultOpen
            nested
          />
        ))}
      </div>
    </details>
  );
}
