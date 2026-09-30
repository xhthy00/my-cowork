import { ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { navigateToModelsConfig, type useModels } from "@/hooks/useModels";
import {
  capabilityFor,
  EFFORT_LABELS,
  reasoningAdapter,
  type ModelCatalog,
} from "../../../../electron/model_capabilities";
import type { ReasoningSelection } from "@/window";

export default function ChatModelSelect({
  modelState,
  catalog,
  value,
  onChange,
  onModelChange,
  error,
  running,
}: {
  modelState: ReturnType<typeof useModels>;
  catalog: ModelCatalog;
  value: ReasoningSelection;
  onChange: (value: ReasoningSelection) => void;
  onModelChange?: (id: string) => void;
  error?: string;
  running?: boolean;
}) {
  const { models, active, setActive } = modelState;
  const [open, setOpen] = useState(false);
  const [budget, setBudget] = useState("");
  const cap = active ? capabilityFor(active, catalog) : undefined;
  const adapter = active ? reasoningAdapter(active, cap) : "default";
  const available = adapter !== "default" && cap?.reasoning !== false;
  const efforts = available
    ? cap?.options.find((o) => o.type === "effort")?.values
    : undefined;
  const toggle = available && cap?.options.some((o) => o.type === "toggle");
  const budgetOption = available
    ? cap?.options.find((o) => o.type === "budget_tokens")
    : undefined;
  const adjustable = Boolean(efforts?.length || budgetOption);
  const parts: string[] = [];
  if (error) parts.push("检查选项");
  else {
    if (value.effort) parts.push(EFFORT_LABELS[value.effort] ?? value.effort);
    if (value.budgetTokens !== undefined)
      parts.push(`${value.budgetTokens.toLocaleString()} tokens`);
    if (!parts.length && adjustable) parts.push("默认");
  }
  const label = [active?.name || active?.model || "选择模型", ...parts].join(
    " · ",
  );
  const triggerClass =
    "inline-flex min-w-0 max-w-[260px] items-center gap-1 rounded-lg px-2 py-1 text-body-xs text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-border-neutral-strong-default";
  if (!models.profiles.length)
    return (
      <button
        type="button"
        className={triggerClass}
        onClick={navigateToModelsConfig}
      >
        配置模型
      </button>
    );
  function choose(next: ReasoningSelection) {
    onChange(next);
  }
  return (
    <DropdownMenu
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setBudget(value.budgetTokens?.toString() ?? "");
      }}
    >
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={triggerClass}
          aria-label={label}
          title={running ? "更改将用于下一次发送" : label}
        >
          <span className="truncate">{label}</span>
          <ChevronDown size={12} className="shrink-0" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        side="top"
        sideOffset={8}
        className="w-[280px] max-w-[calc(100vw-32px)] p-1.5"
        aria-label="模型与思考"
      >
        <DropdownMenuRadioGroup
          value={active?.id ?? ""}
          onValueChange={(id) => {
            if (id !== active?.id) {
              void setActive(id);
              onModelChange?.(id);
            }
          }}
          aria-label="模型"
        >
          {models.profiles.map((p) => {
            const duplicate = models.profiles.some(
              (other) => other.id !== p.id && other.name === p.name,
            );
            return (
              <DropdownMenuRadioItem
                key={p.id}
                value={p.id}
                onSelect={(e) => e.preventDefault()}
                className="rounded-lg py-2"
              >
                <span className="min-w-0">
                  <span className="block truncate">{p.name || p.model}</span>
                  {duplicate && (
                    <span className="block truncate text-body-xs text-ds-text-neutral-muted-default">
                      {models.connections?.find((c) => c.id === p.connectionId)
                        ?.name || p.model}
                    </span>
                  )}
                </span>
                {p.isValid === false && (
                  <span className="ml-auto text-body-xs text-ds-text-neutral-muted-default">
                    待检查
                  </span>
                )}
              </DropdownMenuRadioItem>
            );
          })}
        </DropdownMenuRadioGroup>
        {(adjustable || Object.keys(value).length > 0 || error) && (
          <>
            <DropdownMenuSeparator />
            {error && (
              <p
                role="alert"
                className="px-2 py-1 text-body-xs text-ds-text-danger-default-default"
              >
                {error}，请选择服务默认或重新选择。
              </p>
            )}
            <DropdownMenuLabel className="text-body-xs font-normal text-ds-text-neutral-muted-default">
              思考设置
            </DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={
                Object.values(value).every((v) => v === undefined)
                  ? "default"
                  : "custom"
              }
              onValueChange={() => choose({})}
            >
              <DropdownMenuRadioItem
                value="default"
                onSelect={(e) => e.preventDefault()}
                className="rounded-lg"
              >
                服务默认
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            {efforts?.length ? (
              <DropdownMenuRadioGroup
                aria-label="思考强度"
                value={value.effort ?? ""}
                onValueChange={(effort) =>
                  choose({
                    ...value,
                    effort,
                    enabled: undefined,
                    ...(["google", "openrouter"].includes(adapter)
                      ? { budgetTokens: undefined }
                      : {}),
                  })
                }
              >
                {efforts.map((effort) => (
                  <DropdownMenuRadioItem
                    key={effort}
                    value={effort}
                    onSelect={(e) => e.preventDefault()}
                    className="rounded-lg"
                  >
                    {EFFORT_LABELS[effort] ?? effort}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            ) : null}
            {budgetOption && (
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>思考预算</DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="w-56 p-3">
                  <label className="text-body-xs">
                    预算（tokens）
                    <input
                      aria-label="思考预算"
                      type="number"
                      min={budgetOption.min ?? 0}
                      max={budgetOption.max}
                      value={budget}
                      placeholder="服务默认"
                      onChange={(e) => setBudget(e.target.value)}
                      onKeyDown={(e) => e.stopPropagation()}
                      className="mt-2 w-full rounded-lg border border-ds-border-neutral-subtle-default bg-transparent px-2 py-1.5"
                    />
                  </label>
                  <DropdownMenuItem
                    className="mt-2 justify-center"
                    onSelect={() =>
                      choose({
                        ...value,
                        budgetTokens: budget ? Number(budget) : undefined,
                        ...(budget
                          ? { enabled: toggle ? true : undefined }
                          : {}),
                        ...(["google", "openrouter"].includes(adapter)
                          ? { effort: undefined }
                          : {}),
                      })
                    }
                  >
                    应用预算
                  </DropdownMenuItem>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            )}
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={navigateToModelsConfig}
          className="text-ds-text-neutral-muted-default"
        >
          管理模型
        </DropdownMenuItem>
        {running && (
          <p className="px-2 py-1 text-body-xs text-ds-text-neutral-muted-default">
            更改用于下一次发送
          </p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
