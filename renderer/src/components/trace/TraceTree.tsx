import {
  Background,
  Controls,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect } from "react";

import type { TraceEdge, TraceNode } from "../../store/session";

interface TraceTreeProps {
  nodes: TraceNode[];
  edges: TraceEdge[];
}

const NODE_WIDTH = 140;
const NODE_HEIGHT = 40;
const VERTICAL_GAP = 24;

function buildFlowNodes(nodes: TraceNode[]): Node[] {
  const depths: Record<string, number> = {};
  const children: Record<string, string[]> = {};

  for (const node of nodes) {
    children[node.id] = [];
  }
  for (const node of nodes) {
    if (node.parent && children[node.parent]) {
      children[node.parent].push(node.id);
    }
  }

  function computeDepth(id: string): number {
    if (depths[id] !== undefined) return depths[id];
    const node = nodes.find((n) => n.id === id);
    if (!node) return 0;
    if (!node.parent) {
      depths[id] = 0;
      return 0;
    }
    depths[id] = computeDepth(node.parent) + 1;
    return depths[id];
  }

  for (const node of nodes) {
    computeDepth(node.id);
  }

  const byDepth: Record<number, string[]> = {};
  for (const node of nodes) {
    const d = depths[node.id];
    byDepth[d] = byDepth[d] || [];
    byDepth[d].push(node.id);
  }

  const positions: Record<string, { x: number; y: number }> = {};
  const maxDepth = Math.max(0, ...Object.keys(byDepth).map(Number));
  const centerX = 0;

  for (let d = 0; d <= maxDepth; d++) {
    const ids = byDepth[d] || [];
    const totalWidth = ids.length * NODE_WIDTH + (ids.length - 1) * 24;
    let x = centerX - totalWidth / 2 + NODE_WIDTH / 2;
    const y = d * (NODE_HEIGHT + VERTICAL_GAP);
    for (const id of ids) {
      positions[id] = { x: x - NODE_WIDTH / 2, y };
      x += NODE_WIDTH + 24;
    }
  }

  return nodes.map((node) => ({
    id: node.id,
    position: positions[node.id] ?? { x: 0, y: 0 },
    data: { label: node.label },
    type: "default",
  }));
}

function buildFlowEdges(edges: TraceEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
  }));
}

export default function TraceTree({ nodes, edges }: TraceTreeProps) {
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    setFlowNodes(buildFlowNodes(nodes));
    setFlowEdges(buildFlowEdges(edges));
  }, [nodes, edges, setFlowNodes, setFlowEdges]);

  return (
    <div style={{ width: "100%", height: "240px" }}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        attributionPosition="bottom-left"
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
