import { describe, expect, it } from "vitest";

import { orbStateFromSubject } from "../../renderer/src/components/chat/ThoughtDisplay";

describe("orbStateFromSubject", () => {
  it("maps search / browse copy to searching", () => {
    expect(orbStateFromSubject("正在搜索资料")).toBe("searching");
    expect(orbStateFromSubject("开始分析任务")).toBe("searching");
  });

  it("maps generation copy to composing", () => {
    expect(orbStateFromSubject("正在生成回答")).toBe("composing");
  });

  it("maps tool execution to working", () => {
    expect(orbStateFromSubject("正在执行 · exec.bash")).toBe("working");
    expect(orbStateFromSubject("运行中 · document_agent")).toBe("working");
  });

  it("falls back to breathing", () => {
    expect(orbStateFromSubject("")).toBe("breathing");
    expect(orbStateFromSubject(null)).toBe("breathing");
  });
});
