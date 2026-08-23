import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { usePageTabStore } from "@/store/pageTab";

const ONBOARDING_KEY = "my-cowork-workspace-onboarding-checked";
const DISMISS_KEY = "my-cowork-workspace-onboarding-dismissed";

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

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

export default function OnboardingHint() {
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const [checked, setChecked] = useState<Set<number>>(readChecked);
  const [dismissed, setDismissed] = useState(readDismissed);

  useEffect(() => {
    localStorage.setItem(ONBOARDING_KEY, JSON.stringify([...checked]));
  }, [checked]);

  const next = STEPS.find((step) => !checked.has(step.id));
  if (dismissed || !next) return null;

  function complete(id: number) {
    const finishingLast =
      id === LAST_STEP_ID &&
      checked.size === STEPS.length - 1 &&
      !checked.has(id);

    setChecked((prev) => {
      const nextSet = new Set(prev);
      nextSet.add(id);
      return nextSet;
    });

    if (id === 1) {
      window.dispatchEvent(
        new CustomEvent("my-cowork:navigate", { detail: "connectors" }),
      );
    } else if (finishingLast) {
      setHubTab("settings");
    }
  }

  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Ignore quota / private-mode failures.
    }
  }

  return (
    <div className="mt-3 flex w-full items-start gap-2 rounded-xl bg-ds-bg-neutral-subtle-default px-3 py-2">
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        onClick={() => complete(next.id)}
      >
        <div className="text-body-sm font-medium text-ds-text-neutral-default-default">
          下一步：{next.title}
        </div>
        <div className="mt-0.5 text-label-xs text-ds-text-neutral-muted-default">
          {next.subtitle}
        </div>
      </button>
      <button
        type="button"
        className="mt-0.5 rounded-md p-0.5 text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-strong-default hover:text-ds-text-neutral-default-default"
        aria-label="关闭入门提示"
        onClick={dismiss}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
