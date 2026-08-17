/**
 * Adapted from eigent: pages/Agents/components/SkillListItem.tsx
 */
import {
  Bot,
  Check,
  ChevronRight,
  Ellipsis,
  MessageSquare,
  Plus,
  Trash2,
  Users,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { usePageTabStore } from "@/store/pageTab";
import { useSessionsStore } from "@/store/sessions";

export interface SkillScope {
  isGlobal: boolean;
  selectedAgents: string[];
}

export interface SkillItem {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  schedule?: string | null;
  isExample?: boolean;
  scope: SkillScope;
}

const WORKER_OPTIONS = [
  { value: "developer_agent", label: "开发智能体" },
  { value: "browser_agent", label: "浏览器智能体" },
  { value: "document_agent", label: "文档智能体" },
  { value: "multi_modal_agent", label: "多模态智能体" },
];

interface DefaultProps {
  variant?: "default";
  skill: SkillItem;
  onToggle: (enabled: boolean) => void;
  onScopeChange: (scope: SkillScope) => void;
  onDelete?: () => void;
}

interface PlaceholderProps {
  variant: "placeholder";
  message: string;
  addButtonText?: string;
  onAddClick?: () => void;
}

type SkillListItemProps = DefaultProps | PlaceholderProps;

export default function SkillListItem(props: SkillListItemProps) {
  const [scopeOpen, setScopeOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  if (props.variant === "placeholder") {
    const isClickable = props.onAddClick != null;
    return (
      <div
        role={isClickable ? "button" : undefined}
        tabIndex={isClickable ? 0 : undefined}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-3 rounded-2xl bg-ds-bg-neutral-subtle-default px-6 py-8 transition-colors",
          isClickable && "cursor-pointer hover:bg-ds-bg-neutral-strong-default",
        )}
        onClick={isClickable ? props.onAddClick : undefined}
        onKeyDown={
          isClickable
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  props.onAddClick?.();
                }
              }
            : undefined
        }
      >
        <p className="text-body-sm text-ds-text-neutral-muted-default">{props.message}</p>
        {isClickable && <Plus className="h-4 w-4 text-ds-icon-neutral-default-default" />}
      </div>
    );
  }

  const { skill, onToggle, onScopeChange, onDelete } = props;
  const isAllAgentsSelected = skill.scope.isGlobal;

  const handleToggleAllAgents = () => {
    if (isAllAgentsSelected) {
      onScopeChange({ isGlobal: false, selectedAgents: [] });
    } else {
      onScopeChange({ isGlobal: true, selectedAgents: [] });
    }
  };

  const handleToggleAgent = (agentValue: string) => {
    if (isAllAgentsSelected) {
      onScopeChange({
        isGlobal: false,
        selectedAgents: WORKER_OPTIONS.filter((a) => a.value !== agentValue).map(
          (a) => a.value,
        ),
      });
      return;
    }
    const selected = skill.scope.selectedAgents.includes(agentValue);
    onScopeChange({
      isGlobal: false,
      selectedAgents: selected
        ? skill.scope.selectedAgents.filter((a) => a !== agentValue)
        : [...skill.scope.selectedAgents, agentValue],
    });
  };

  const handleTryInChat = () => {
    useSessionsStore.getState().createSession(skill.name);
    usePageTabStore.getState().setWorkspaceView("workspace");
    window.dispatchEvent(
      new CustomEvent("my-cowork:composer-fill", {
        detail: `我刚添加了 {{${skill.name}}} 技能，请用它帮我做点有意思的事。`,
      }),
    );
  };

  return (
    <div
      className={cn(
        "flex w-full flex-col justify-between rounded-2xl bg-ds-bg-neutral-subtle-default p-4 transition-colors",
        skill.isExample && !skill.enabled && "opacity-50",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="truncate text-sm font-bold text-ds-text-neutral-default-default">
          {skill.name}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          <Switch checked={skill.enabled} onCheckedChange={onToggle} />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled={!skill.enabled}
            title="在对话中试用"
            onClick={skill.enabled ? handleTryInChat : undefined}
          >
            <MessageSquare className="h-4 w-4" />
          </Button>
          {!skill.isExample && onDelete && (
            <div className="relative">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="更多"
                onClick={() => setMenuOpen((v) => !v)}
              >
                <Ellipsis className="h-4 w-4" />
              </Button>
              {menuOpen && (
                <>
                  <button
                    type="button"
                    className="fixed inset-0 z-10 cursor-default"
                    aria-label="关闭菜单"
                    onClick={() => setMenuOpen(false)}
                  />
                  <div className="absolute right-0 z-20 mt-1 w-36 rounded-xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default p-1 shadow-sm">
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-[var(--danger)] hover:bg-ds-bg-neutral-subtle-default"
                      onClick={() => {
                        setMenuOpen(false);
                        onDelete();
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      删除
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <p
        className="mt-2 line-clamp-5 break-words text-body-sm text-ds-text-neutral-muted-default"
        title={skill.description}
      >
        {skill.description || skill.id}
      </p>

      {skill.schedule && (
        <code className="mt-2 text-[11px] text-ds-text-neutral-subtle-default">
          {skill.schedule}
        </code>
      )}

      <div className="mt-2 flex flex-col items-start gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn("px-0", scopeOpen ? "opacity-100" : "opacity-50")}
          onClick={() => setScopeOpen((v) => !v)}
        >
          选择智能体访问权限
          <ChevronRight className={cn("h-4 w-4", scopeOpen && "-rotate-90")} />
        </Button>

        {scopeOpen && (
          <div className="flex w-full flex-wrap items-center gap-2 border-t border-ds-border-neutral-default-default pt-4">
            <button
              type="button"
              onClick={handleToggleAllAgents}
              className={cn(
                "inline-flex items-center gap-2 rounded-full bg-ds-bg-neutral-default-default px-2 py-1 text-[11px] font-medium text-ds-text-neutral-default-default transition-opacity",
                isAllAgentsSelected ? "opacity-100" : "opacity-60",
              )}
            >
              {isAllAgentsSelected ? (
                <Check size={16} className="text-ds-icon-status-completed-default-default" />
              ) : (
                <Users size={16} />
              )}
              全部智能体
            </button>
            {WORKER_OPTIONS.map((agent) => {
              const isSelected =
                isAllAgentsSelected || skill.scope.selectedAgents.includes(agent.value);
              return (
                <button
                  key={agent.value}
                  type="button"
                  onClick={() => handleToggleAgent(agent.value)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full bg-ds-bg-neutral-default-default px-2 py-1 text-[11px] font-medium transition-opacity",
                    isSelected ? "opacity-100" : "opacity-50",
                  )}
                >
                  {isSelected ? (
                    <Check size={16} className="text-ds-icon-status-completed-default-default" />
                  ) : (
                    <Bot size={16} />
                  )}
                  {agent.label}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
