/**
 * @vitest-environment jsdom
 */

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TraceTree from "../../renderer/src/components/trace/TraceTree";
import type { TraceEdge, TraceNode } from "../../renderer/src/store/session";

beforeEach(() => {
  globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }));
});

describe("TraceTree", () => {
  it("renders 2 nodes from a step + tool fixture", () => {
    const nodes: TraceNode[] = [
      { id: "step-1", type: "step", label: "supervisor" },
      { id: "tool-1", type: "tool", label: "pptx.gen", parent: "step-1" },
    ];
    const edges: TraceEdge[] = [
      { id: "e-step-1-tool-1", source: "step-1", target: "tool-1" },
    ];

    render(<TraceTree nodes={nodes} edges={edges} />);

    expect(screen.getByText("supervisor")).toBeInTheDocument();
    expect(screen.getByText("pptx.gen")).toBeInTheDocument();
  });
});
