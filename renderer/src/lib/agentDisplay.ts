/**
 * Adapted from eigent: components/WorkFlow/agents.tsx (display subset for Agent Pool).
 */
export type WorkflowAgentType =
  | "developer_agent"
  | "browser_agent"
  | "document_agent"
  | "multi_modal_agent";

export type AgentDisplayInfo = {
  name: string;
  textColor: string;
};

export const agentMap: Record<WorkflowAgentType, AgentDisplayInfo> = {
  developer_agent: {
    name: "开发智能体",
    textColor: "text-ds-text-terminal-default-default",
  },
  browser_agent: {
    name: "浏览器智能体",
    textColor: "text-blue-700",
  },
  document_agent: {
    name: "文档智能体",
    textColor: "text-yellow-700",
  },
  multi_modal_agent: {
    name: "多模态智能体",
    textColor: "text-fuchsia-700",
  },
};

export function isWorkflowAgentType(type: string): type is WorkflowAgentType {
  return type in agentMap;
}
