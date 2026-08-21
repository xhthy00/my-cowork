/**
 * Compact context-window ring (WorkBuddy-style).
 * Hover shows occupancy copy: ``51.2% · 98.2K / 192.0K 上下文已使用``.
 */
import { formatContextUsedLabel, formatTokenCount } from "@/lib/formatTokens";
import { cn } from "@/lib/utils";
import { useState } from "react";

interface ContextUsageIndicatorProps {
  used: number;
  limit: number;
  inputTokens?: number;
  outputTokens?: number;
  size?: number;
}

export default function ContextUsageIndicator({
  used,
  limit,
  inputTokens = 0,
  outputTokens = 0,
  size = 16,
}: ContextUsageIndicatorProps) {
  const [hover, setHover] = useState(false);
  const hasDenominator = limit > 0;
  const percentage = hasDenominator ? Math.min(100, (Math.max(0, used) / limit) * 100) : 0;
  const isWarning = percentage > 70;
  const isDanger = percentage > 90;
  const label = formatContextUsedLabel(used, limit);

  const strokeWidth = 2;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  const strokeColor = isDanger
    ? "var(--danger)"
    : isWarning
      ? "var(--warning)"
      : "var(--ds-text-information-default-default)";
  const trackColor = "var(--ds-border-neutral-subtle-default)";

  const parts: string[] = [];
  if (inputTokens > 0) parts.push(`输入 ${formatTokenCount(inputTokens)}`);
  if (outputTokens > 0) parts.push(`输出 ${formatTokenCount(outputTokens)}`);

  return (
    <div
      className="relative inline-flex shrink-0 cursor-default items-center justify-center"
      style={{ width: size, height: size }}
      title={label}
      aria-label={label}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percentage)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={trackColor} strokeWidth={strokeWidth} />
        {hasDenominator && percentage > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            style={{ transition: "stroke-dashoffset 0.3s ease, stroke 0.3s ease" }}
          />
        )}
      </svg>
      {hover && (
        <div
          className={cn(
            "absolute bottom-full left-1/2 z-[200] mb-1 -translate-x-1/2",
            "rounded-lg border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default",
            "px-2 py-1.5 shadow-lg whitespace-nowrap",
          )}
        >
          <div className="text-label-xs font-medium text-ds-text-neutral-default-default">{label}</div>
          {parts.length > 0 && (
            <div className="mt-0.5 text-[11px] text-ds-text-neutral-subtle-default">{parts.join(" · ")}</div>
          )}
        </div>
      )}
    </div>
  );
}
