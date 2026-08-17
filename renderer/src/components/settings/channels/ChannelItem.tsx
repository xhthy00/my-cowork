import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import ChannelHeader, { type ChannelCardConfig } from "./ChannelHeader";

export default function ChannelItem({
  channel,
  children,
  onToggleEnabled,
  defaultOpen = false,
}: {
  channel: ChannelCardConfig;
  children: ReactNode;
  onToggleEnabled?: (enabled: boolean) => void;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      data-channel-id={channel.id}
      className="overflow-hidden rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-default-default"
    >
      <div className="flex w-full items-center gap-2 px-3 py-3">
        <div className="min-w-0 flex-1">
          <ChannelHeader channel={channel} onToggleEnabled={onToggleEnabled} />
        </div>
        <button
          type="button"
          className="shrink-0 rounded-md p-1 text-ds-icon-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default"
          aria-expanded={open}
          aria-label={open ? `收起${channel.title}` : `展开${channel.title}`}
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronDown
            size={16}
            className={cn("transition-transform", open ? "rotate-180" : "")}
          />
        </button>
      </div>
      {open ? (
        <div className="border-t border-ds-border-neutral-subtle-default px-4 py-4">
          {children}
        </div>
      ) : null}
    </div>
  );
}
