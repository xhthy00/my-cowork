/**
 * Adapted from eigent: ChatBox/TaskBox/PlanTaskBox
 * (FoldedView surface + SubtaskEditor rows + BottomBox confirm CTA).
 */
import { CircleDashed } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PlanSubTask } from "../../types/workforce";
import { useWorkforceStore } from "../../store/workforce";

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

export default function PlanTaskBox() {
  const pending = useWorkforceStore((s) => s.pendingPlan);
  const clearPendingPlan = useWorkforceStore((s) => s.clearPendingPlan);
  const seedPlan = useWorkforceStore((s) => s.seedPlan);
  const [rows, setRows] = useState<PlanSubTask[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const inputRefs = useRef<Array<HTMLTextAreaElement | null>>([]);

  const subtasks = rows ?? pending?.subtasks ?? [];

  useEffect(() => {
    setRows(null);
  }, [pending?.taskId]);

  useEffect(() => {
    if (focusIndex === null) return;
    const el = inputRefs.current[focusIndex];
    if (el) {
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
    setFocusIndex(null);
  }, [focusIndex, subtasks.length]);

  if (!pending) return null;

  function updateRow(index: number, content: string) {
    setRows(
      subtasks.map((row, i) => (i === index ? { ...row, content } : row)),
    );
  }

  function addRow() {
    setRows([
      ...subtasks,
      {
        id: `task_${subtasks.length + 1}`,
        content: "",
        assignee: "developer_agent",
        dependencies: [],
      },
    ]);
    setFocusIndex(subtasks.length);
  }

  function deleteRow(index: number) {
    if (subtasks.length <= 1) return;
    setRows(subtasks.filter((_, i) => i !== index));
    setFocusIndex(Math.max(0, index - 1));
  }

  function handleKey(
    e: KeyboardEvent<HTMLTextAreaElement>,
    index: number,
    content: string,
  ) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      addRow();
      return;
    }
    if (e.key === "Backspace" && content === "" && subtasks.length > 1) {
      e.preventDefault();
      deleteRow(index);
    }
  }

  async function confirm() {
    if (!pending || busy) return;
    const cleaned = subtasks
      .map((t) => ({ ...t, content: t.content.trim() }))
      .filter((t) => t.content.length > 0);
    if (!cleaned.length) return;
    setBusy(true);
    try {
      const backendUrl = await window.api.getBackendUrl();
      if (!backendUrl) return;
      await fetch(`${backendUrl}/api/workforce/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_id: pending.taskId,
          subtasks: cleaned,
        }),
      });
      // Lock Progress to the user-confirmed plan (status refined by SSE later).
      seedPlan(
        cleaned.map((t) => ({
          id: t.id,
          content: t.content,
          status: "waiting" as const,
          agent: t.assignee,
          terminal: [],
        })),
      );
      clearPendingPlan();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={cn(
        "relative mb-3 flex w-full flex-col overflow-hidden rounded-2xl",
        "bg-ds-bg-splitting-subtle-default",
      )}
    >
      <div className="flex items-center gap-2 border-x-0 border-b border-t-0 border-solid border-ds-border-neutral-subtle-default px-3 py-2">
        <div className="min-w-0 flex-1 truncate text-left text-body-sm font-bold text-ds-text-neutral-default-default">
          子任务规划
        </div>
      </div>

      <div className="relative m-2 max-h-[240px] overflow-y-auto rounded-xl bg-transparent">
        <div className="flex flex-col px-1 py-1">
          {subtasks.map((t, index) => (
            <div
              key={t.id}
              className="flex items-start gap-2 p-1 duration-300 animate-in fade-in-0 slide-in-from-left-2"
            >
              <div className="flex h-6 shrink-0 items-center justify-center">
                <CircleDashed
                  size={16}
                  className="mt-0.5 fill-current text-ds-icon-status-splitting-default-default"
                />
              </div>
              <textarea
                ref={(el) => {
                  inputRefs.current[index] = el;
                  autoResize(el);
                }}
                value={t.content}
                placeholder={
                  index === subtasks.length - 1 ? "添加子任务…" : ""
                }
                rows={1}
                onChange={(e) => {
                  updateRow(index, e.target.value);
                  autoResize(e.currentTarget);
                }}
                onKeyDown={(e) => handleKey(e, index, t.content)}
                className="min-w-0 flex-1 resize-none border-none bg-transparent text-body-sm font-normal leading-6 text-ds-text-neutral-default-default outline-none placeholder:text-ds-text-neutral-subtle-default focus:outline-none"
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 px-3 pb-3 pt-1">
        <Button
          type="button"
          size="sm"
          disabled={busy || subtasks.every((t) => !t.content.trim())}
          onClick={() => void confirm()}
          className={cn(
            "!rounded-full !border-[var(--colors-green-default)] !bg-[var(--colors-green-default)] !text-white",
            "hover:!opacity-90",
          )}
        >
          {busy ? "启动中…" : "开始任务"}
        </Button>
      </div>
    </div>
  );
}
