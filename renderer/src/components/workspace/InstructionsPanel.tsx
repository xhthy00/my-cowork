/**
 * Adapted from eigent: Workspace/WorkspaceCoworkPanel.tsx
 */
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { isMemoryEnabled, setMemoryEnabled } from "@/components/memory/MemoryView";
import {
  SESSION_SIDE_PANEL_CONTENT_WIDTH_CLASS,
} from "@/components/session/sessionSidePanelLayout";
import { usePageTabStore } from "@/store/pageTab";

const ONBOARDING_KEY = "my-cowork-workspace-onboarding-checked";

const STEPS = [
  {
    id: 1,
    title: "连接日常工具",
    subtitle: "越了解你的环境，就越好用。",
  },
  {
    id: 2,
    title: "组建多智能体团队",
    subtitle: "添加 worker，为项目组建智能体团队。",
  },
  {
    id: 3,
    title: "让助手创建内容",
    subtitle: "让助手创建表格、文档、演示或你需要的任何内容。",
  },
  {
    id: 4,
    title: "安排周期性任务",
    subtitle: "把重复工作变成自动流程，适合提醒、报告与定期更新。",
  },
] as const;

const LAST_STEP_ID = STEPS[STEPS.length - 1].id;

function readChecked(): Set<number> {
  try {
    const v = localStorage.getItem(ONBOARDING_KEY);
    return v ? new Set(JSON.parse(v) as number[]) : new Set();
  } catch {
    return new Set();
  }
}

function StepCard({
  id,
  title,
  subtitle,
  checked,
  onClick,
}: {
  id: number;
  title: string;
  subtitle: string;
  checked: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "group flex w-full items-start gap-2 rounded-xl bg-ds-bg-neutral-subtle-default p-2 text-left transition-colors",
        checked
          ? "cursor-default"
          : "cursor-pointer hover:bg-ds-bg-neutral-strong-default",
      )}
      onClick={checked ? undefined : onClick}
      aria-pressed={checked}
    >
      <div
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full",
          checked
            ? "bg-ds-bg-success-default-default"
            : "bg-ds-bg-neutral-muted-default",
        )}
      >
        {checked ? (
          <Check
            className="h-2.5 w-2.5 text-ds-text-success-inverse-default"
            aria-hidden
          />
        ) : (
          <span className="text-[8px] font-bold leading-none text-ds-text-neutral-muted-default">
            {id}
          </span>
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <span
          className={cn(
            "text-body-sm font-semibold",
            checked
              ? "text-ds-text-neutral-muted-default"
              : "text-ds-text-neutral-default-default",
          )}
        >
          {title}
        </span>
        <span className="mt-1 text-label-xs text-ds-text-neutral-muted-default">
          {subtitle}
        </span>
      </div>
    </button>
  );
}

export default function InstructionsPanel() {
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const [memoryOn, setMemoryOn] = useState(isMemoryEnabled);
  const [checked, setChecked] = useState<Set<number>>(readChecked);
  const [guideOpen, setGuideOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(ONBOARDING_KEY, JSON.stringify([...checked]));
  }, [checked]);

  const allChecked = checked.size >= STEPS.length;

  function handleCheckStep(id: number) {
    const isFirstCompletion =
      id === LAST_STEP_ID &&
      checked.size === STEPS.length - 1 &&
      !checked.has(id);

    setChecked((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });

    if (id === 1) {
      window.dispatchEvent(
        new CustomEvent("my-cowork:navigate", { detail: "connectors" }),
      );
    } else if (isFirstCompletion) {
      setHubTab("settings");
    }
  }

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col overflow-hidden py-1 pr-1",
        SESSION_SIDE_PANEL_CONTENT_WIDTH_CLASS,
      )}
    >
      <div className="flex shrink-0 flex-col gap-0.5 rounded-2xl bg-ds-bg-neutral-default-default px-2 py-1">
        <div className="shrink-0 px-2 py-1.5">
          <span className="text-body-sm font-semibold text-ds-text-neutral-default-default">
            指引
          </span>
        </div>
        <div className="flex min-w-0 items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-ds-bg-neutral-strong-default">
          <span className="min-w-0 text-body-sm font-medium text-ds-text-neutral-muted-default">
            记忆
          </span>
          <Button
            type="button"
            variant="secondary"
            size="xs"
            className="shrink-0"
            onClick={() => {
              const next = !memoryOn;
              setMemoryOn(next);
              setMemoryEnabled(next);
            }}
            aria-pressed={memoryOn}
            aria-label={`记忆: ${memoryOn ? "开" : "关"}`}
          >
            {memoryOn ? "开" : "关"}
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto py-2">
        {allChecked ? (
          <div className="overflow-hidden rounded-xl">
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-xl px-4 py-2.5 text-left text-body-sm font-medium hover:bg-ds-bg-neutral-default-default"
              onClick={() => setGuideOpen((v) => !v)}
              aria-expanded={guideOpen}
            >
              <span className="min-w-0 flex-1 truncate font-semibold text-ds-text-neutral-default-default">
                入门指南
              </span>
              <span className="shrink-0 text-body-xs text-ds-text-neutral-muted-default">
                {checked.size}/{STEPS.length}
              </span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 text-ds-icon-neutral-muted-default transition-transform",
                  guideOpen && "rotate-180",
                )}
                aria-hidden
              />
            </button>
            {guideOpen && (
              <div className="flex flex-col gap-2 px-2 pb-2">
                {STEPS.map((step) => (
                  <StepCard
                    key={step.id}
                    id={step.id}
                    title={step.title}
                    subtitle={step.subtitle}
                    checked
                    onClick={() => {}}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {STEPS.map((step) => (
              <StepCard
                key={step.id}
                id={step.id}
                title={step.title}
                subtitle={step.subtitle}
                checked={checked.has(step.id)}
                onClick={() => handleCheckStep(step.id)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
