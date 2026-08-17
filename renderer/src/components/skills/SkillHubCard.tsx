import { Check, KeyRound, Plus, Star } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface HubSkill {
  name: string;
  description: string;
  iconUrl?: string | null;
  downloads: number;
  stars: number;
  category: string;
  slug: string;
  handle: string;
  version: string;
  requiresApiKey: boolean;
  homepage: string;
}

export function formatCount(n: number): string {
  if (n >= 1_000_000) return `${Math.round(n / 1_000_000)}m`;
  if (n >= 1000) return `${Math.round(n / 1000)}k`;
  return String(n);
}

interface SkillHubCardProps {
  skill: HubSkill;
  installed: boolean;
  installing: boolean;
  onInstall: () => void;
}

export default function SkillHubCard({
  skill,
  installed,
  installing,
  onInstall,
}: SkillHubCardProps) {
  const [iconFailed, setIconFailed] = useState(false);
  const showIcon = Boolean(skill.iconUrl) && !iconFailed;

  return (
    <div className="flex flex-col rounded-2xl bg-ds-bg-neutral-subtle-default p-4">
      <div className="mb-2 flex items-start gap-2">
        {showIcon ? (
          <img
            src={skill.iconUrl!}
            alt=""
            referrerPolicy="no-referrer"
            className="h-8 w-8 shrink-0 rounded-md object-cover"
            onError={() => setIconFailed(true)}
          />
        ) : (
          <div className="h-8 w-8 shrink-0 rounded-md bg-ds-bg-neutral-strong-default" />
        )}
        <div className="min-w-0 flex-1 font-semibold text-ds-text-neutral-default-default">
          {skill.name}
        </div>
        <Button
          variant="ghost"
          size="icon"
          disabled={installed || installing}
          aria-label={installed ? `已安装 ${skill.name}` : `安装 ${skill.name}`}
          onClick={onInstall}
        >
          {installed ? (
            <Check className="h-4 w-4" />
          ) : (
            <Plus className={cn("h-4 w-4", installing && "opacity-40")} />
          )}
        </Button>
      </div>
      <p className="mb-3 line-clamp-3 flex-1 text-sm text-ds-text-neutral-muted-default">
        {skill.description || "暂无描述"}
      </p>
      <div className="flex items-center gap-3 text-xs text-ds-text-neutral-muted-default">
        <span>{formatCount(skill.downloads)}</span>
        <span className="inline-flex items-center gap-0.5">
          <Star className="h-3 w-3" />
          {formatCount(skill.stars)}
        </span>
        {skill.requiresApiKey && (
          <span className="inline-flex items-center gap-0.5">
            <KeyRound className="h-3 w-3" />
            需 API Key
          </span>
        )}
      </div>
    </div>
  );
}
