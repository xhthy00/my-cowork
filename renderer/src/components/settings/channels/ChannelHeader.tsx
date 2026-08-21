import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import { getChannelLogo } from "./channelLogos";

export interface ChannelCardConfig {
  id: string;
  title: string;
  description: string;
  comingSoon?: boolean;
  enabled: boolean;
  disabled?: boolean;
  accent: string;
  initial: string;
}

export default function ChannelHeader({
  channel,
  onToggleEnabled,
}: {
  channel: ChannelCardConfig;
  onToggleEnabled?: (enabled: boolean) => void;
}) {
  const logoSrc = getChannelLogo(channel.id);

  return (
    <div className="flex w-full items-center gap-3">
      {logoSrc ? (
        <img
          src={logoSrc}
          alt=""
          className={cn(
            "h-8 w-8 shrink-0 rounded-lg object-contain",
            channel.comingSoon && "opacity-60",
          )}
        />
      ) : (
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[12px] font-bold text-white",
            channel.accent,
          )}
        >
          {channel.initial}
        </span>
      )}
      <div className="min-w-0 flex-1 text-left">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-medium text-ds-text-neutral-default-default">
            {channel.title}
          </span>
          {channel.comingSoon ? (
            <span className="rounded bg-ds-bg-neutral-subtle-default px-1.5 py-0.5 text-[11px] text-ds-text-neutral-muted-default">
              即将推出
            </span>
          ) : null}
        </div>
        <div className="truncate text-[12px] text-ds-text-neutral-muted-default">
          {channel.description}
        </div>
      </div>
      <div
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <Switch
          checked={channel.enabled}
          disabled={channel.disabled || channel.comingSoon}
          onCheckedChange={(v) => onToggleEnabled?.(v)}
          aria-label={`启用${channel.title}`}
        />
      </div>
    </div>
  );
}
