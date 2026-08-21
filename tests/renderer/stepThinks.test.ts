import { describe, expect, it } from "vitest";

import {
  assignThinksToSteps,
  collectStepThinks,
} from "../../renderer/src/lib/stepThinks";
import type { TraceEvent } from "../../renderer/src/store/session";

function ev(type: string, payload: Record<string, unknown>, id = type): TraceEvent {
  return { id, type, payload };
}

describe("collectStepThinks", () => {
  it("extracts tagged think and closes on </think>", () => {
    const thinks = collectStepThinks([
      ev("graph.step", { node: "single_agent", id: "n1" }, "n1"),
      ev("step.delta", { delta: "<think>", agent_id: "single_agent" }),
      ev("step.delta", { delta: "planning the search", agent_id: "single_agent" }),
      ev("step.delta", { delta: "</think>\n", agent_id: "single_agent" }),
      ev("step.delta", { delta: "我先梳理任务。", agent_id: "single_agent" }),
    ]);
    expect(thinks).toHaveLength(1);
    expect(thinks[0]?.text).toContain("planning the search");
    expect(thinks[0]?.text).not.toContain("我先梳理");
    expect(thinks[0]?.closed).toBe(true);
  });

  it("treats MiniMax orphan </think> as closed think", () => {
    const thinks = collectStepThinks([
      ev("step.delta", { delta: "内部推理扬州限购", agent_id: "single_agent" }),
      ev("step.delta", { delta: "</think>\n扬州已取消限购。", agent_id: "single_agent" }),
    ]);
    expect(thinks[0]?.text).toContain("内部推理扬州限购");
    expect(thinks[0]?.text).not.toContain("扬州已取消限购");
    expect(thinks[0]?.closed).toBe(true);
  });

  it("keeps live think open until the step finishes", () => {
    const thinks = collectStepThinks([
      ev("step.delta", { delta: "<think>still going", agent_id: "single_agent" }),
    ]);
    expect(thinks[0]?.closed).toBe(false);
    expect(thinks[0]?.text).toContain("still going");
  });

  it("starts a new think after tool.start", () => {
    const thinks = collectStepThinks([
      ev("step.delta", { delta: "<think>first</think>", agent_id: "single_agent" }),
      ev("tool.start", { agent_id: "single_agent", tool: "web_search", call_id: "c1" }),
      ev("step.delta", { delta: "<think>second", agent_id: "single_agent" }),
    ]);
    expect(thinks).toHaveLength(2);
    expect(thinks[0]?.text).toContain("first");
    expect(thinks[0]?.closed).toBe(true);
    expect(thinks[0]?.stepId).toBe("c1");
    expect(thinks[1]?.text).toContain("second");
    expect(thinks[1]?.closed).toBe(false);
  });

  it("binds each think to the following tool, not the graph.step node", () => {
    const thinks = collectStepThinks([
      ev("graph.step", { node: "single_agent", id: "n1" }, "n1"),
      ev("step.delta", { delta: "<think>why search</think>", agent_id: "single_agent" }),
      ev("tool.start", { agent_id: "single_agent", tool: "web_search", call_id: "c1" }),
      ev("step.delta", { delta: "<think>why fetch</think>", agent_id: "single_agent" }),
      ev("tool.start", { agent_id: "single_agent", tool: "web_fetch", call_id: "c2" }),
    ]);
    expect(thinks.map((t) => t.stepId)).toEqual(["c1", "c2"]);
    expect(thinks[0]?.text).toContain("why search");
    expect(thinks[1]?.text).toContain("why fetch");
  });

  it("closes remaining thinks on graph.end", () => {
    const thinks = collectStepThinks([
      ev("step.delta", { delta: "<think>plan", agent_id: "single_agent" }),
      ev("graph.end", { status: "ok" }),
    ]);
    expect(thinks[0]?.closed).toBe(true);
  });
});

describe("assignThinksToSteps", () => {
  it("attaches a think to the matching tool row, not the top of the list", () => {
    const thinks = collectStepThinks([
      ev("graph.step", { node: "single_agent", id: "n1" }, "n1"),
      ev("step.delta", { delta: "<think>why search</think>", agent_id: "single_agent" }),
      ev("tool.start", { agent_id: "single_agent", tool: "web_search", call_id: "c1" }),
      ev("step.delta", { delta: "<think>why write</think>", agent_id: "single_agent" }),
      ev("tool.start", { agent_id: "single_agent", tool: "fs.write", call_id: "c2" }),
    ]);
    const { byStep, leftover } = assignThinksToSteps(thinks, [
      { id: "prep", kind: "prep" },
      { id: "n1", agentId: "single_agent", kind: "tool" },
      { id: "c1", agentId: "single_agent", kind: "tool" },
      { id: "c2", agentId: "single_agent", kind: "tool" },
    ]);
    expect(leftover).toHaveLength(0);
    expect(byStep.get("n1")).toBeUndefined();
    expect(byStep.get("c1")?.[0]?.text).toContain("why search");
    expect(byStep.get("c2")?.[0]?.text).toContain("why write");
  });

  it("parks a live think under the latest tool of that agent", () => {
    const thinks = collectStepThinks([
      ev("tool.start", { agent_id: "single_agent", tool: "web_search", call_id: "c1" }),
      ev("step.delta", { delta: "<think>still going", agent_id: "single_agent" }),
    ]);
    const { byStep, leftover } = assignThinksToSteps(thinks, [
      { id: "c1", agentId: "single_agent", kind: "tool" },
    ]);
    expect(leftover).toHaveLength(0);
    expect(byStep.get("c1")?.[0]?.text).toContain("still going");
  });
});
