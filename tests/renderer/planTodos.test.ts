import { describe, expect, it } from "vitest";

import { planTodosFromQuery } from "../../renderer/src/lib/planTodos";
import { buildProgressItems } from "../../renderer/src/lib/progressFromTrace";

describe("planTodosFromQuery", () => {
  it("does not seed a fake planning step", () => {
    expect(planTodosFromQuery("帮我将这篇博客转成md文件")).toEqual([]);
  });
});

describe("buildProgressItems", () => {
  it("uses live tools when Progress has not been todo_write yet", () => {
    const items = buildProgressItems(
      [],
      [
        {
          id: "1",
          type: "tool.result",
          payload: { tool: "fs_write", call_id: "c1" },
        },
        {
          id: "2",
          type: "tool.result",
          payload: { tool: "bash", call_id: "c2" },
        },
      ],
      false,
    );
    expect(items.map((i) => i.content).join(" ")).not.toMatch(/规划任务步骤/);
    expect(items.length).toBeGreaterThan(0);
    expect(items.at(-1)?.status).toBe("running");
  });

  it("prefers real todo_write rows over trace fallback", () => {
    const items = buildProgressItems(
      [
        {
          id: "todo_1",
          content: "抓取文章",
          status: "completed",
          agent: "single_agent",
          terminal: [],
        },
        {
          id: "todo_2",
          content: "写成 Markdown",
          status: "running",
          agent: "single_agent",
          terminal: [],
        },
      ],
      [{ id: "1", type: "tool.result", payload: { tool: "bash" } }],
      false,
    );
    expect(items.map((i) => i.content)).toEqual(["抓取文章", "写成 Markdown"]);
  });
});
