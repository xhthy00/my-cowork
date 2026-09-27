/** @vitest-environment jsdom */

import { afterEach, describe, expect, it } from "vitest";

import { useSessionsStore } from "../../renderer/src/store/sessions";

describe("legacy session titles", () => {
  afterEach(() => {
    localStorage.removeItem("my-cowork-sessions");
    useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
  });

  it("recovers saved 任务中 titles from the first user message", async () => {
    localStorage.setItem("my-cowork-sessions", JSON.stringify({
      version: 2,
      state: {
        activeId: null,
        sessions: [
          { id: "with-query", title: "任务中", status: "done" },
          { id: "empty", title: "任务中", status: "idle" },
          { id: "named", title: "我的自定义标题", status: "done" },
        ],
        messagesById: {
          "with-query": [
            { id: "u1", role: "user", content: "整理季度报告\n[附件: /tmp/report.docx]" },
          ],
          named: [{ id: "u2", role: "user", content: "另一条提问" }],
        },
      },
    }));

    await useSessionsStore.persist.rehydrate();

    const titles = useSessionsStore.getState().sessions.map((session) => session.title);
    expect(titles).toEqual(["整理季度报告", "新对话", "我的自定义标题"]);
  });
});
