/**
 * Token context usage ring indicator.
 * Adapted from AionUi ContextUsageIndicator — shows a circular progress ring
 * with token usage percentage, hover popover with breakdown.
 */
import { formatTokenCount } from "@/lib/formatTokens";
import { cn } from "@/lib/utils";
import { useState } from "react";

interface ContextUsageIndicatorProps {
  budgetTokens: number;
  budgetMaxTokens: number;
  contextLimit: number;
  inputTokens: number;
  outputTokens: number;
  size?: number;
}

export default function ContextUsageIndicator({
  budgetTokens,
  budgetMaxTokens,
  contextLimit,
  inputTokens,
  outputTokens,
  size = 20,
}: ContextUsageIndicatorProps) {
  const [hover, setHover] = useState(false);

  // Use context_limit if available, otherwise fall back to budget max.
  const denominator = contextLimit > 0 ? contextLimit : budgetMaxTokens;
  const hasDenominator = denominator > 0;
  const percentage = hasDenominator ? Math.min(100, (budgetTokens / denominator) * 100) : 0;
  const isWarning = percentage > 70;
  const isDanger = percentage > 90;

  if (budgetTokens <= 0) return null;

  const strokeWidth = 2.5;
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

  const popover = hasDenominator ? (
    <div className="p-2 min-w-[160px]">
      <div className="text-sm font-medium text-ds-text-neutral-default-default">
        {percentage.toFixed(1)}% · {formatTokenCount(budgetTokens)} / {formatTokenCount(denominator)}
      </div>
      {parts.length > 0 && (
        <div className="mt-1 text-xs text-ds-text-neutral-subtle-default">{parts.join(" · ")}</div>
      )}
    </div>
  ) : (
    <div className="p-2 min-w-[160px]">
      <div className="text-sm font-medium text-ds-text-neutral-default-default">
        {formatTokenCount(budgetTokens)} tokens
      </div>
      <div className="mt-1 text-xs text-ds-text-neutral-subtle-default">上下文窗口大小未知</div>
    </div>
  );

  return (
    <div
      className="relative inline-flex shrink-0 cursor-pointer items-center justify-center"
      style={{ width: size, height: size }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={trackColor} strokeWidth={strokeWidth} />
        {hasDenominator && (
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
            "absolute bottom-full left-0 z-[200] mb-1",
            "rounded-lg border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default",
            "shadow-lg whitespace-nowrap",
          )}
        >
          {popover}
        </div>
      )}
    </div>
  );
}
