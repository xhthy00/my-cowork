import { formatContextUsedLabel, formatTokenCount } from "@/lib/formatTokens";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ContextUsageIndicatorProps {
  used: number;
  limit: number;
  inputTokens?: number;
  outputTokens?: number;
  size?: number;
  trigger?: number;
  compacted?: boolean;
  busy?: boolean;
  canCompact?: boolean;
  onCompact?: () => void;
}
export default function ContextUsageIndicator({
  used,
  limit,
  size = 16,
  trigger,
  compacted,
  busy,
  canCompact,
  onCompact,
}: ContextUsageIndicatorProps) {
  const percentage =
    limit > 0 ? Math.min(100, (Math.max(0, used) / limit) * 100) : 0;
  const radius = (size - 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const label = formatContextUsedLabel(used, limit);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`上下文用量：${label}`}
          title={label}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-border-neutral-strong-default"
        >
          <svg
            width={size}
            height={size}
            viewBox={`0 0 ${size} ${size}`}
            style={{ transform: "rotate(-90deg)" }}
            aria-hidden
          >
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="var(--ds-border-neutral-subtle-default)"
              strokeWidth={2}
            />
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={percentage >= 90 ? "var(--warning)" : "currentColor"}
              strokeWidth={2}
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - percentage / 100)}
              strokeLinecap="round"
            />
          </svg>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side="top"
        sideOffset={8}
        className="w-[280px] p-2"
        aria-label="当前对话上下文"
      >
        <div className="px-2 py-2 text-body-xs">
          <p className="mb-3 text-body-sm font-medium">当前对话</p>
          <dl className="grid grid-cols-2 gap-y-2">
            <dt>已用（估算）</dt>
            <dd className="text-right">{formatTokenCount(used)}</dd>
            <dt>上下文窗口</dt>
            <dd className="text-right">
              {limit > 0 ? formatTokenCount(limit) : "待获取"}
            </dd>
            {trigger !== undefined && (
              <>
                <dt>压缩触发上限</dt>
                <dd className="text-right">{formatTokenCount(trigger)}</dd>
              </>
            )}
          </dl>
          <p className="mt-3 text-ds-text-neutral-muted-default">
            {busy
              ? "任务运行中"
              : compacted
                ? "较早对话已压缩，原文保留"
                : "历史与草稿估算，系统提示和工具另计。"}
          </p>
          {trigger !== undefined && (
            <p className="mt-1 text-ds-text-neutral-muted-default">
              实际压缩会计入系统提示和工具。
            </p>
          )}
        </div>
        {onCompact && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              disabled={busy || !canCompact}
              onSelect={onCompact}
            >
              压缩对话
            </DropdownMenuItem>
            <p className="px-2 pb-1 text-[11px] text-ds-text-neutral-muted-default">
              调用当前模型，消耗 tokens；原文保留。
            </p>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
