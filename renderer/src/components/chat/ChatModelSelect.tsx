import { Check, ChevronDown, Key, Server } from "lucide-react";
import { useMemo, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { navigateToModelsConfig, useModels } from "@/hooks/useModels";
import { resolvePresetId } from "@/lib/modelPresets";
import {
  getModelImage,
  isDarkAppearance,
  needsInvertModelImage,
} from "@/lib/modelProviderImages";
import { cn } from "@/lib/utils";
import type { ModelProfile } from "@/window";

/** Matches Eigent ModelSelect trigger shell. */
const modelTriggerShellClass = cn(
  "rounded-xl px-2 py-1 inline-flex max-w-[min(100%,420px)] shrink-0 items-center gap-1.5",
  "bg-ds-bg-neutral-default-default text-ds-text-neutral-default-default",
);

/** Vendor name + concrete model id, e.g. `Minimax (MiniMax-M3)`. */
function formatModelLabel(profile: ModelProfile): string {
  const model = profile.model?.trim();
  if (!model || model === profile.name) return profile.name;
  return `${profile.name} (${model})`;
}

function VendorIcon({
  profile,
  size = "sm",
}: {
  profile: ModelProfile;
  size?: "sm" | "xs";
}) {
  const appearance = isDarkAppearance() ? "dark" : "light";
  const logoId = resolvePresetId(profile);
  const logo = getModelImage(logoId);
  const box = size === "xs" ? "h-3.5 w-3.5" : "h-4 w-4";
  if (logo) {
    return (
      <img
        src={logo}
        alt=""
        className={cn(box, "shrink-0")}
        style={
          needsInvertModelImage(logoId, appearance)
            ? { filter: "invert(1)" }
            : undefined
        }
      />
    );
  }
  if (
    profile.category === "local" ||
    profile.provider === "ollama" ||
    profile.provider === "lmstudio" ||
    profile.provider === "vllm"
  ) {
    return <Server className={cn(box, "shrink-0 text-ds-text-neutral-muted-default")} />;
  }
  return <Key className={cn(box, "shrink-0 text-ds-text-neutral-muted-default")} />;
}

function ProfileRow({
  profile,
  preferred,
  onSelect,
}: {
  profile: ModelProfile;
  preferred: boolean;
  onSelect: () => void;
}) {
  const configured = profile.isValid !== false;
  const label = formatModelLabel(profile);
  return (
    <DropdownMenuItem
      className="flex items-center justify-between gap-2"
      onClick={onSelect}
      title={label}
    >
      <div className="flex min-w-0 items-center gap-2">
        <VendorIcon profile={profile} />
        <span
          className={cn(
            "truncate text-body-sm",
            configured
              ? "text-ds-text-neutral-default-default"
              : "text-ds-text-neutral-muted-default",
          )}
        >
          {label}
        </span>
      </div>
      <div className="flex items-center gap-1">
        {!configured && (
          <div className="h-2 w-2 rounded-full bg-ds-text-neutral-default-default opacity-10" />
        )}
        {preferred && (
          <Check className="h-4 w-4 text-ds-text-success-default-default" />
        )}
        {configured && !preferred && (
          <div className="h-2 w-2 rounded-full bg-ds-text-success-default-default" />
        )}
      </div>
    </DropdownMenuItem>
  );
}

export default function ChatModelSelect() {
  const { models, active, setActive, switching, status } = useModels();
  const [open, setOpen] = useState(false);

  const custom = useMemo(
    () =>
      models.profiles.filter(
        (p) =>
          p.category !== "local" &&
          p.provider !== "ollama" &&
          p.provider !== "lmstudio" &&
          p.provider !== "vllm",
      ),
    [models.profiles],
  );
  const local = useMemo(
    () =>
      models.profiles.filter(
        (p) =>
          p.category === "local" ||
          p.provider === "ollama" ||
          p.provider === "lmstudio" ||
          p.provider === "vllm",
      ),
    [models.profiles],
  );

  const triggerName = active ? formatModelLabel(active) : "选择默认模型";

  if (models.profiles.length === 0) {
    return (
      <button
        type="button"
        className={cn(
          modelTriggerShellClass,
          "cursor-pointer border-0 text-left hover:bg-ds-bg-neutral-subtle-default",
        )}
        onClick={navigateToModelsConfig}
        aria-label="去配置模型"
      >
        <span className="min-w-0 truncate !text-label-xs font-semibold">
          去配置模型
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-80" strokeWidth={2} />
      </button>
    );
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          disabled={switching}
          title={status || triggerName}
          aria-label={triggerName}
          aria-haspopup="menu"
          className={cn(
            modelTriggerShellClass,
            "min-w-0 cursor-pointer border-0 text-left",
            "duration-[160ms] ease-[cubic-bezier(0.23,1,0.32,1)] justify-between font-semibold transition-[background-color,box-shadow,opacity]",
            "hover:bg-ds-bg-neutral-subtle-default active:bg-ds-bg-neutral-subtle-default data-[state=open]:bg-ds-bg-neutral-subtle-default",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-border-neutral-strong-default focus-visible:ring-offset-2",
            "disabled:pointer-events-none disabled:opacity-50",
            open && "min-w-[200px]",
          )}
        >
          <span className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
            {active && <VendorIcon profile={active} size="xs" />}
            <span className="min-w-0 flex-1 truncate text-left !text-label-xs text-ds-text-neutral-default-default">
              {triggerName}
            </span>
          </span>
          <ChevronDown
            className="h-3.5 w-3.5 shrink-0 opacity-80"
            aria-hidden
            strokeWidth={2}
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side="top"
        sideOffset={4}
        className="w-[240px]"
      >
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="flex w-full min-w-0 items-center justify-start gap-2">
            <Key className="h-4 w-4 shrink-0 text-ds-text-neutral-default-default" />
            <span className="min-w-0 flex-1 text-left text-body-sm">自定义模型</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="max-h-[300px] w-[240px] overflow-y-auto">
            {custom.length === 0 ? (
              <DropdownMenuItem onClick={navigateToModelsConfig}>
                <span className="text-body-sm text-ds-text-neutral-muted-default">
                  去配置…
                </span>
              </DropdownMenuItem>
            ) : (
              custom.map((p) => (
                <ProfileRow
                  key={p.id}
                  profile={p}
                  preferred={models.activeId === p.id}
                  onSelect={() => {
                    void setActive(p.id);
                    setOpen(false);
                  }}
                />
              ))
            )}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="flex w-full min-w-0 items-center justify-start gap-2">
            <Server className="h-4 w-4 shrink-0 text-ds-text-neutral-default-default" />
            <span className="min-w-0 flex-1 text-left text-body-sm">本地模型</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="max-h-[300px] w-[240px] overflow-y-auto">
            {local.length === 0 ? (
              <DropdownMenuItem onClick={navigateToModelsConfig}>
                <span className="text-body-sm text-ds-text-neutral-muted-default">
                  去配置…
                </span>
              </DropdownMenuItem>
            ) : (
              local.map((p) => (
                <ProfileRow
                  key={p.id}
                  profile={p}
                  preferred={models.activeId === p.id}
                  onSelect={() => {
                    void setActive(p.id);
                    setOpen(false);
                  }}
                />
              ))
            )}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
