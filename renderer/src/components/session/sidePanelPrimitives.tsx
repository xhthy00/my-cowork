/**
 * Adapted from eigent: Session/SidePanelSections/primitives.tsx
 */
import { Check } from "lucide-react";
import { forwardRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export function CountPill({ count }: { count: number }) {
  return (
    <span className="inline-flex items-center justify-center rounded-full bg-ds-bg-neutral-subtle-default px-1.5 text-[10px] font-bold text-ds-text-neutral-subtle-default">
      {count}
    </span>
  );
}

export function CategoryLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "px-1 pb-1 pt-2 text-[11px] text-ds-text-neutral-muted-default first:pt-0",
        className,
      )}
    >
      {children}
    </div>
  );
}

type SidePanelListRowProps = {
  leading?: ReactNode;
  children: ReactNode;
  trailing?: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  interactiveHover?: boolean;
  className?: string;
};

export const SidePanelListRow = forwardRef<HTMLElement, SidePanelListRowProps>(
  (
    {
      leading,
      children,
      trailing,
      disabled,
      onClick,
      interactiveHover,
      className,
    },
    ref,
  ) => {
    const showAffordance = Boolean(onClick || interactiveHover);
    const base = cn(
      "group flex min-w-0 w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left text-body-sm text-ds-text-neutral-default-default transition-colors",
      disabled
        ? "pointer-events-none opacity-50"
        : showAffordance
          ? "cursor-pointer hover:bg-ds-bg-neutral-subtle-default"
          : "",
      className,
    );

    const content = (
      <>
        {leading ? <span className="flex shrink-0 items-center">{leading}</span> : null}
        <span className="min-w-0 flex-1 truncate">{children}</span>
        {trailing ? <span className="flex shrink-0 items-center">{trailing}</span> : null}
      </>
    );

    if (onClick) {
      return (
        <button
          ref={ref as React.Ref<HTMLButtonElement>}
          type="button"
          onClick={onClick}
          disabled={disabled}
          className={base}
        >
          {content}
        </button>
      );
    }

    return (
      <div ref={ref as React.Ref<HTMLDivElement>} className={base}>
        {content}
      </div>
    );
  },
);
SidePanelListRow.displayName = "SidePanelListRow";

export function ProgressCircle({
  done,
  running = false,
  size = 14,
}: {
  done: boolean;
  running?: boolean;
  size?: number;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full border-[0.5px] border-solid",
        done
          ? "border-ds-bg-success-default-default bg-ds-bg-success-default-default text-ds-text-success-inverse-default"
          : running
            ? "progress-dot-running border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default"
            : "border-ds-border-neutral-default-default bg-ds-bg-neutral-subtle-default",
      )}
      style={{ width: size, height: size }}
      aria-hidden
    >
      {done ? (
        <Check
          className="!text-ds-text-success-inverse-default"
          size={Math.max(8, size - 6)}
          strokeWidth={4}
        />
      ) : null}
    </span>
  );
}

export function ProgressConnector() {
  return (
    <span className="h-px min-w-[6px] flex-1 bg-ds-border-neutral-default-default" aria-hidden />
  );
}
