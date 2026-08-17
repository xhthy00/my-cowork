/**
 * Workforce topology view — list + topology graph.
 * Adapted from eigent WorkFlow (ReactFlow) + AionUi team panel.
 */
import { Network, List } from "lucide-react";
import { useMemo, useState } from "react";
import {
  type Node as FlowNode,
  type NodeTypes,
  ReactFlow,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useWorkforceStore } from "../../store/workforce";
import AgentTaskCard from "./AgentTaskCard";
import { cn } from "@/lib/utils";

type ViewMode = "list" | "topology";

const AGENT_META: Record<string, { color: string; label: string }> = {
  developer_agent: { color: "#10b981", label: "开发" },
  browser_agent: { color: "#3b82f6", label: "浏览" },
  document_agent: { color: "#f59e0b", label: "文档" },
  multi_modal_agent: { color: "#8b5cf6", label: "多模态" },
  supervisor: { color: "#6b7280", label: "协调" },
  coordinator: { color: "#6b7280", label: "协调" },
  single_agent: { color: "#10b981", label: "单智能体" },
};

function statusColor(status?: string): string {
  if (status === "running") return "#10b981";
  if (status === "done") return "#3b82f6";
  if (status === "error") return "#ef4444";
  return "#9ca3af";
}

function TopologyNode({ data }: { data: { agent: { agent_id: string; name: string; type: string; status?: string; tasks: { id: string; content: string; status?: string }[]; progress?: { completed: number; total: number } } } }) {
  const agent = data.agent;
  const meta = AGENT_META[agent.type] ?? { color: "#6b7280", label: "Agent" };
  const borderColor = statusColor(agent.status);
  const runningTask = agent.tasks.find((t) => t.status === "running");

  return (
    <div
      className="rounded-xl border-2 bg-white px-3 py-2 shadow-md dark:bg-zinc-900"
      style={{ borderColor, minWidth: 160, maxWidth: 220 }}
    >
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.color }} />
        <span className="text-sm font-semibold">{agent.name}</span>
      </div>
      {runningTask && (
        <div className="mt-1 truncate text-xs text-gray-500">
          {runningTask.content || runningTask.id}
        </div>
      )}
      {agent.progress && agent.progress.total > 0 && (
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${(agent.progress.completed / agent.progress.total) * 100}%`,
              backgroundColor: meta.color,
            }}
          />
        </div>
      )}
    </div>
  );
}

const nodeTypes: NodeTypes = {
  agent: TopologyNode as unknown as NodeTypes[string],
};

function buildTopologyNodes(
  agents: { agent_id: string; name: string; type: string; status?: string; tasks: { id: string; content: string; status?: string }[]; progress?: { completed: number; total: number } }[],
): FlowNode[] {
  if (agents.length === 0) return [];
  const hasSupervisor = agents.some((a) => a.type === "supervisor" || a.type === "coordinator");
  const centerY = (agents.length - 1) * 60;

  const nodes: FlowNode[] = [];

  if (hasSupervisor) {
    const sv = agents.find((a) => a.type === "supervisor" || a.type === "coordinator")!;
    nodes.push({
      id: sv.agent_id,
      type: "agent",
      position: { x: 0, y: centerY },
      data: { agent: sv },
    });
  }

  const workers = agents.filter((a) => a.type !== "supervisor" && a.type !== "coordinator");
  workers.forEach((agent, i) => {
    const y = i * 120;
    nodes.push({
      id: agent.agent_id,
      type: "agent",
      position: { x: 280, y },
      data: { agent },
    });
  });

  return nodes;
}

export default function WorkforceTopologyView() {
  const agents = useWorkforceStore((s) => s.taskAssigning);
  const taskRunning = useWorkforceStore((s) => s.taskRunning);
  const [viewMode, setViewMode] = useState<ViewMode>("list");

  const initialNodes = useMemo(() => buildTopologyNodes(agents), [agents]);
  const [nodes, , onNodesChange] = useNodesState(initialNodes);

  const runningCount = agents.filter((a) => a.status === "running").length;
  const completedCount = agents.filter((a) => a.status === "done" || a.status === "error").length;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {/* Header: view toggle + stats */}
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-1.5 text-[12px] text-ds-text-neutral-muted-default">
          <span className="font-semibold text-ds-text-neutral-default-default">{agents.length}</span>
          智能体
          {runningCount > 0 && (
            <span className="ml-1 inline-flex items-center gap-1">
              · <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--colors-green-default)]" />
              {runningCount} 运行
            </span>
          )}
          {taskRunning.length > 0 && (
            <span className="ml-1">· {taskRunning.length} 任务</span>
          )}
        </div>
        <div className="flex items-center gap-0.5 rounded-lg bg-ds-bg-neutral-strong-default p-0.5">
          <button
            type="button"
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-md transition-colors",
              viewMode === "list" ? "bg-ds-bg-neutral-subtle-default" : "hover:bg-ds-bg-neutral-subtle-default",
            )}
            title="列表视图"
            onClick={() => setViewMode("list")}
          >
            <List className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-md transition-colors",
              viewMode === "topology" ? "bg-ds-bg-neutral-subtle-default" : "hover:bg-ds-bg-neutral-subtle-default",
            )}
            title="拓扑视图"
            onClick={() => setViewMode("topology")}
          >
            <Network className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Content */}
      {viewMode === "list" ? (
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="flex flex-col gap-1.5 pb-2">
            {agents.map((agent) => (
              <AgentTaskCard
                key={agent.agent_id}
                agent={agent}
                defaultExpanded={agent.status === "running"}
              />
            ))}
            {agents.length === 0 && (
              <div className="py-8 text-center text-[13px] text-ds-text-neutral-subtle-default">
                暂无智能体
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 overflow-hidden rounded-xl border border-ds-border-neutral-subtle-default">
          <ReactFlow
            nodes={nodes}
            onNodesChange={onNodesChange}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            proOptions={{ hideAttribution: true }}
            nodesDraggable
            zoomOnScroll
            panOnDrag
          />
        </div>
      )}
    </div>
  );
}
