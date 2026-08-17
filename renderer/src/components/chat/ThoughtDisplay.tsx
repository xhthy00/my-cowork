/**
 * Agent thinking process display.
 * Ported 1:1 from AionUi ThoughtDisplay (packages/desktop/src/renderer/components/chat/ThoughtDisplay.tsx) —
 * gradient card with spinner, subject Tag, truncated description and elapsed timer.
 * Arco Tag/Spin/UnoCSS classes are adapted to Tailwind + design tokens.
 */
import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface ThoughtData {
  subject: string;
  description: string;
}

type ThoughtDisplayProps = {
  thought?: ThoughtData | null;
  style?: "default" | "compact";
  running?: boolean;
  statusText?: string;
  onStop?: () => void;
  // Directed per-member attach retry, shown next to a runtime-failed status text.
  onRetryStart?: () => void;
  // Absolute start timestamp (ms) supplied by an external source (e.g. team slot work).
  startedAtMs?: number | null;
  // Explicit flag declaring elapsed time is driven by an external timestamp (team chain).
  externalElapsedSource?: boolean;
};

// Container class names mirrored from AionUi (UnoCSS → Tailwind):
// relative z-1 mb--20px pb-30px px-10px py-10px rd-t-20px text-14px lh-20px
// Note: AionUi's negative bottom margin fused the card into the composer, but
// here it dragged the composer upward — use a normal gap and full rounding.
const BASE_CLASS =
  "relative z-[1] mb-2 px-[10px] py-[10px] rounded-2xl bg-ds-bg-neutral-default-default text-[14px] leading-[20px] text-ds-text-neutral-default-default";

const ThoughtDisplay = ({
  thought,
  style = "default",
  running = false,
  statusText,
  onStop: _onStop,
  onRetryStart,
  startedAtMs,
  externalElapsedSource,
}: ThoughtDisplayProps) => {
  // Format elapsed time with localized units
  const formatElapsedTime = (seconds: number): string => {
    const sUnit = "s";
    const mUnit = "m";

    if (seconds < 60) {
      return `${seconds}${sUnit}`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}${mUnit} ${remainingSeconds}${sUnit}`;
  };

  const [elapsedTime, setElapsedTime] = useState(0);
  const startTimeRef = useRef<number>(Date.now());

  // External mode with a valid absolute start timestamp → derive elapsed from it (state A).
  const hasValidStartedAt =
    externalElapsedSource === true &&
    typeof startedAtMs === "number" &&
    Number.isFinite(startedAtMs) &&
    startedAtMs > 0;
  // External mode but timestamp invalid → suppress the elapsed number (state B).
  const suppressElapsed = externalElapsedSource === true && !hasValidStartedAt;
  // Show the elapsed number only while running and not suppressed; the spinner stays gated on `running`.
  const showElapsed = running && !suppressElapsed;

  // Timer for elapsed time
  useEffect(() => {
    // Branch A: external timestamp mode with a valid start. Base the elapsed time on the
    // absolute `startedAtMs`, so remount or effect re-runs recompute from the same origin
    // instead of resetting to zero.
    if (
      externalElapsedSource === true &&
      typeof startedAtMs === "number" &&
      Number.isFinite(startedAtMs) &&
      startedAtMs > 0
    ) {
      const tick = () => setElapsedTime(Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000)));
      tick();
      const timer = setInterval(tick, 1000);
      return () => clearInterval(timer);
    }

    // Branch B: external timestamp mode without a valid start. Do not start a timer; the
    // render layer suppresses the number and only shows the status text and spinner.
    if (externalElapsedSource === true) {
      setElapsedTime(0);
      return;
    }

    // Branch C: non-external mode (non-team). Preserve the original local timer behavior.
    if (!running && !thought?.subject) {
      setElapsedTime(0);
      return;
    }

    startTimeRef.current = Date.now();
    setElapsedTime(0);

    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
      setElapsedTime(elapsed);
    }, 1000);

    return () => clearInterval(timer);
  }, [externalElapsedSource, startedAtMs, running, thought?.subject]);

  // Gradient backgrounds mirrored from AionUi (light / dark theme).
  const containerStyle =
    style === "compact"
      ? { maxHeight: "100px", overflow: "scroll" as const, marginBottom: "8px" }
      : undefined;

  // Hide when not running and no thought data
  if (!thought?.subject && !running && !statusText) {
    return null;
  }

  // Loading-only mode: running without thought data (used by ACP when thinking is inline)
  if (!thought?.subject && (running || statusText)) {
    return (
      <div className={cn(BASE_CLASS, "flex items-center gap-[8px]")} style={containerStyle}>
        {running && <Loader2 size={14} className="shrink-0 animate-spin text-ds-text-neutral-muted-default" />}
        {/* Left block fills the row and truncates long text (tooltip shows the
            full message); the retry button stays pinned on the right and never
            shrinks, so a long/localized status can't push it out of a narrow
            parallel-view column. */}
        <span className="min-w-0 flex-1 truncate text-ds-text-neutral-muted-default" title={statusText}>
          {statusText ?? "正在处理"}
          {showElapsed && <span className="ml-[8px] opacity-60">({formatElapsedTime(elapsedTime)})</span>}
        </span>
        {onRetryStart && (
          <button
            type="button"
            className="shrink-0 cursor-pointer text-[12px] text-ds-text-information-default-default hover:opacity-80"
            onClick={onRetryStart}
          >
            重新开始
          </button>
        )}
      </div>
    );
  }

  // Full thought display mode: used by non-ACP platforms that still pass thought data
  const showDescription = thought?.description && thought.description !== thought.subject;

  return (
    <div className={BASE_CLASS} style={containerStyle}>
      <div className="flex items-center gap-[8px]">
        {running && <Loader2 size={14} className="shrink-0 animate-spin text-ds-text-neutral-muted-default" />}
        <span className="inline-flex h-[20px] shrink-0 items-center whitespace-nowrap rounded-sm bg-ds-bg-neutral-subtle-default px-[8px] text-[12px] leading-none text-ds-text-information-default-default">
          {thought?.subject}
        </span>
        {showDescription && (
          <span className="min-w-0 flex-1 truncate" title={thought?.description}>
            {thought?.description}
          </span>
        )}
        {showElapsed && (
          <span className="whitespace-nowrap text-[12px] text-ds-text-neutral-subtle-default">
            ({formatElapsedTime(elapsedTime)})
          </span>
        )}
      </div>
    </div>
  );
};

export default ThoughtDisplay;
