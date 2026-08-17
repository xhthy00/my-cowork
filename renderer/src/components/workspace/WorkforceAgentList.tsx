/**
 * Adapted from eigent: WorkforceAgentList + FoldedAgentCard (compact + context menu).
 */
import {
  Bot,
  CodeXml,
  Copy,
  FileText,
  Globe,
  Image,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import AlertDialog from "@/components/ui/alertDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import {
  isBaseWorkforceAgent,
  useWorkforceStore,
} from "@/store/workforce";
import type { WorkforceAgent, WorkerType } from "@/types/workforce";

const WORKER_TYPE_OPTIONS: { value: WorkerType; label: string }[] = [
  { value: "developer_agent", label: "开发智能体" },
  { value: "browser_agent", label: "浏览器智能体" },
  { value: "document_agent", label: "文档智能体" },
  { value: "multi_modal_agent", label: "多模态智能体" },
];

function TypeBadge({ type }: { type: WorkerType | string }) {
  const cls = "h-2.5 w-2.5";
  switch (type) {
    case "developer_agent":
      return <CodeXml className={cls} aria-hidden />;
    case "browser_agent":
      return <Globe className={cls} aria-hidden />;
    case "document_agent":
      return <FileText className={cls} aria-hidden />;
    case "multi_modal_agent":
      return <Image className={cls} aria-hidden />;
    default:
      return null;
  }
}

function AgentLeadingIcon({ type }: { type: WorkerType | string }) {
  const badge = <TypeBadge type={type} />;
  return (
    <div className="relative inline-flex h-6 w-6 shrink-0 items-center justify-center self-center text-ds-text-neutral-muted-default">
      <Bot className="h-6 w-6" strokeWidth={2} aria-hidden />
      {badge && (
        <span className="absolute -right-1 -top-1 inline-flex items-center justify-center text-ds-text-neutral-muted-default [&_svg]:shrink-0">
          {badge}
        </span>
      )}
    </div>
  );
}

function FoldedAgentCard({
  agent,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  agent: WorkforceAgent;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const isBase = isBaseWorkforceAgent(agent.agent_id);
  const shellClass = cn(
    "inline-flex items-center justify-center rounded-xl border-0 bg-ds-bg-neutral-strong-default p-2",
    "text-left outline-none transition-[opacity,box-shadow] duration-200",
    "opacity-80 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-ds-ring-neutral-subtle-default",
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={agent.name}
          aria-haspopup="menu"
          title={agent.name}
          className={shellClass}
        >
          <AgentLeadingIcon type={agent.type} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="bottom" sideOffset={8}>
        <DropdownMenuItem
          className="cursor-pointer gap-2"
          disabled={isBase}
          onSelect={(e) => {
            e.preventDefault();
            if (!isBase) onEdit();
          }}
        >
          <Pencil className="h-4 w-4 shrink-0" aria-hidden />
          编辑
        </DropdownMenuItem>
        <DropdownMenuItem
          className="cursor-pointer gap-2"
          disabled={isBase}
          onSelect={(e) => {
            e.preventDefault();
            if (!isBase) onDuplicate();
          }}
        >
          <Copy className="h-4 w-4 shrink-0" aria-hidden />
          复制
        </DropdownMenuItem>
        <DropdownMenuItem
          className="cursor-pointer gap-2 text-ds-text-error-default-default focus:text-ds-text-error-default-default"
          disabled={isBase}
          onSelect={(e) => {
            e.preventDefault();
            if (!isBase) onDelete();
          }}
        >
          <Trash2 className="h-4 w-4 shrink-0 text-ds-text-error-default-default" aria-hidden />
          删除
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function WorkerFormDialog({
  open,
  title,
  initialName,
  initialType,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  initialName: string;
  initialType: WorkerType;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: (name: string, type: WorkerType) => void;
}) {
  const [name, setName] = useState(initialName);
  const [type, setType] = useState<WorkerType>(initialType);

  return (
    <AlertDialog
      open={open}
      title={title}
      confirmLabel={confirmLabel}
      confirmDisabled={!name.trim()}
      onCancel={onCancel}
      onConfirm={() => {
        const next = name.trim();
        if (!next) return;
        onConfirm(next, type);
      }}
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1.5 text-body-sm">
          <span className="font-medium text-ds-text-neutral-muted-default">名称</span>
          <input
            autoFocus
            value={name}
            placeholder="Worker 名称"
            className="h-9 w-full rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 text-sm outline-none focus:ring-2 focus:ring-ds-ring-neutral-subtle-default"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && name.trim()) onConfirm(name.trim(), type);
            }}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-body-sm">
          <span className="font-medium text-ds-text-neutral-muted-default">类型</span>
          <select
            value={type}
            className="h-9 w-full rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 text-sm outline-none"
            onChange={(e) => setType(e.target.value as WorkerType)}
          >
            {WORKER_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </AlertDialog>
  );
}

export function SingleAgentList() {
  return (
    <div
      className="inline-flex rounded-xl bg-ds-bg-neutral-strong-default p-2"
      aria-hidden
    >
      <Bot
        className="h-6 w-6 shrink-0 text-ds-text-neutral-muted-default"
        strokeWidth={2}
      />
    </div>
  );
}

export function WorkforceAgentList() {
  const agents = useWorkforceStore((s) => s.taskAssigning);
  const upsertAgent = useWorkforceStore((s) => s.upsertAgent);
  const removeAgent = useWorkforceStore((s) => s.removeAgent);
  const duplicateAgent = useWorkforceStore((s) => s.duplicateAgent);

  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<WorkforceAgent | null>(null);

  return (
    <div className="flex w-full min-w-0 justify-center">
      <div className="inline-flex min-w-0 max-w-full items-center gap-2">
        <div
          role="list"
          aria-label="多智能体团队"
          className="min-w-0 max-w-[min(100%,calc(100vw-3rem))] overflow-x-auto"
        >
          <div className="flex flex-row flex-nowrap items-center justify-center gap-2">
            {agents.map((agent) => (
              <div key={agent.agent_id} className="shrink-0" role="listitem">
                <FoldedAgentCard
                  agent={agent}
                  onEdit={() => setEditTarget(agent)}
                  onDuplicate={() => duplicateAgent(agent.agent_id)}
                  onDelete={() => removeAgent(agent.agent_id)}
                />
              </div>
            ))}
          </div>
        </div>
        <button
          type="button"
          title="添加 Worker"
          aria-label="添加 Worker"
          className={cn(
            "inline-flex items-center justify-center rounded-xl border-0 bg-ds-bg-neutral-default-default p-2",
            "text-ds-text-neutral-muted-default opacity-80 transition-[color,opacity] duration-200",
            "hover:text-ds-text-neutral-default-default hover:opacity-100",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-ring-neutral-subtle-default",
          )}
          onClick={() => setAddOpen(true)}
        >
          <Plus className="h-6 w-6 shrink-0" strokeWidth={2} aria-hidden />
        </button>
      </div>

      {addOpen && (
        <WorkerFormDialog
          key="add-worker"
          open={addOpen}
          title="添加 Worker"
          initialName=""
          initialType="developer_agent"
          confirmLabel="添加"
          onCancel={() => setAddOpen(false)}
          onConfirm={(name, type) => {
            const taken = new Set(
              useWorkforceStore.getState().taskAssigning.map((a) => a.agent_id),
            );
            let id = name;
            let n = 2;
            while (taken.has(id)) id = `${name} ${n++}`;
            upsertAgent({ agent_id: id, name, type, status: "idle" });
            setAddOpen(false);
          }}
        />
      )}

      {editTarget && (
        <WorkerFormDialog
          key={`edit-${editTarget.agent_id}`}
          open
          title="编辑 Worker"
          initialName={editTarget.name}
          initialType={
            (WORKER_TYPE_OPTIONS.some((o) => o.value === editTarget.type)
              ? editTarget.type
              : "developer_agent") as WorkerType
          }
          confirmLabel="保存"
          onCancel={() => setEditTarget(null)}
          onConfirm={(name, type) => {
            upsertAgent({
              agent_id: editTarget.agent_id,
              name,
              type,
            });
            setEditTarget(null);
          }}
        />
      )}
    </div>
  );
}
