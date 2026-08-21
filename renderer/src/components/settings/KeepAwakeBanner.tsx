import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

let pendingSettingsTab: "general" | "schedule" | null = null;

export function takeSettingsTabPending(): "general" | "schedule" | null {
  const pending = pendingSettingsTab;
  pendingSettingsTab = null;
  return pending;
}

export function openKeepAwakeSettings(): void {
  pendingSettingsTab = "general";
  window.dispatchEvent(
    new CustomEvent("my-cowork:navigate", { detail: "settings-general" }),
  );
}

export function openScheduleSettings(): void {
  pendingSettingsTab = "schedule";
  window.dispatchEvent(
    new CustomEvent("my-cowork:navigate", { detail: "settings-schedule" }),
  );
}

export default function KeepAwakeBanner({
  message,
  onOpenKeepAwake,
  className,
}: {
  message: string;
  onOpenKeepAwake?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ds-bg-neutral-default-default px-4 py-3",
        className,
      )}
    >
      <p className="min-w-0 text-body-sm text-ds-text-neutral-muted-default">{message}</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onOpenKeepAwake ?? openKeepAwakeSettings}
      >
        打开保持唤醒
      </Button>
    </div>
  );
}

