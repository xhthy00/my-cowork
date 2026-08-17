/**
 * @vitest-environment jsdom
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  abortActiveChatStream,
  abortChatStream,
  trackChatStream,
} from "../../renderer/src/api/chatStream";
import { buildChatHistory } from "../../renderer/src/components/chat/ChatBar";
import {
  dispatchProjectEvent,
  dropProjectPark,
  rememberProjectTaskId,
} from "../../renderer/src/store/livePark";
import { useSessionStore } from "../../renderer/src/store/session";
import { useSessionsStore } from "../../renderer/src/store/sessions";

describe("session isolation", () => {
  beforeEach(() => {
    abortActiveChatStream();
    useSessionsStore.setState({
      sessions: [],
      activeId: null,
      messagesById: {},
    });
    useSessionStore.setState({
      messages: [],
      runStatus: "idle",
      taskStartedAt: null,
      taskElapsedMs: 0,
      trace: [],
      confirmQueue: [],
      pendingArtifacts: [],
      currentStepId: null,
    });
  });

  it("createSession clears live chat so history does not leak", () => {
    useSessionsStore.getState().createSession("旧会话");
    const oldMessages = [
      { id: "u1", role: "user" as const, content: "宜昌旅游攻略" },
      { id: "a1", role: "assistant" as const, content: "这是旧会话内容" },
    ];
    useSessionStore.setState({ messages: oldMessages });

    const second = useSessionsStore.getState().createSession("新对话");
    const first = useSessionsStore.getState().sessions[1]?.id;

    expect(useSessionStore.getState().messages).toEqual([]);
    expect(useSessionsStore.getState().getMessages(second)).toEqual([]);
    expect(first).toBeTruthy();
    expect(useSessionsStore.getState().getMessages(first!)).toEqual(oldMessages);
    expect(buildChatHistory(useSessionsStore.getState().getMessages(second))).toEqual([]);
  });

  it("strips think blocks from follow-up history", () => {
    const history = buildChatHistory([
      { id: "u1", role: "user", content: "写一份评审意见" },
      {
        id: "a1",
        role: "assistant",
        content:
          "<think>I will generate a formal report. Plan the task first.</think>\n评审结论：建议谨慎参股。",
      },
    ]);
    expect(history).toHaveLength(2);
    expect(history[1]?.content).toContain("评审结论");
    expect(history[1]?.content).not.toContain("<think>");
    expect(history[1]?.content).not.toContain("Plan the task");
  });

  it("does not abort in-flight chat stream on session switch", () => {
    const a = useSessionsStore.getState().createSession("a");
    const controller = new AbortController();
    const spy = vi.spyOn(controller, "abort");
    rememberProjectTaskId(a, "task-a");
    trackChatStream("task-a", controller);

    useSessionsStore.getState().createSession("b");
    expect(spy).not.toHaveBeenCalled();
  });

  it("restores running live state when switching back", () => {
    const a = useSessionsStore.getState().createSession("a");
    useSessionStore.setState({
      messages: [
        { id: "u1", role: "user", content: "分析成绩" },
        { id: "a1", role: "assistant", content: "正在写…" },
      ],
      runStatus: "running",
      taskStartedAt: 1_700_000_000_000,
      trace: [{ id: "t1", type: "graph.start", payload: {} }],
    });

    const b = useSessionsStore.getState().createSession("b");
    expect(useSessionStore.getState().runStatus).toBe("idle");
    expect(useSessionStore.getState().messages).toEqual([]);

    useSessionsStore.getState().setActive(a);
    const live = useSessionStore.getState();
    expect(live.runStatus).toBe("running");
    expect(live.taskStartedAt).toBe(1_700_000_000_000);
    expect(live.messages.some((m) => m.content.includes("正在写"))).toBe(true);
    expect(live.trace.some((t) => t.type === "graph.start")).toBe(true);
    expect(b).toBeTruthy();
  });

  it("routes background SSE into parked project without touching active", () => {
    const a = useSessionsStore.getState().createSession("a");
    useSessionStore.setState({
      messages: [{ id: "u1", role: "user", content: "任务A" }],
      runStatus: "running",
      taskStartedAt: Date.now(),
    });
    useSessionsStore.getState().createSession("b");
    expect(useSessionStore.getState().messages).toEqual([]);

    dispatchProjectEvent(a, {
      type: "step.delta",
      payload: { delta: "后台增量" },
    });

    expect(useSessionStore.getState().messages).toEqual([]);
    useSessionsStore.getState().setActive(a);
    const text = useSessionStore
      .getState()
      .messages.map((m) => m.content)
      .join("\n");
    expect(text).toContain("后台增量");
    expect(useSessionStore.getState().runStatus).toBe("running");
  });

  it("deleteSession aborts that project stream only", () => {
    const a = useSessionsStore.getState().createSession("keep");
    const b = useSessionsStore.getState().createSession("drop");
    const keep = new AbortController();
    const drop = new AbortController();
    const keepSpy = vi.spyOn(keep, "abort");
    const dropSpy = vi.spyOn(drop, "abort");
    rememberProjectTaskId(a, "task-keep");
    rememberProjectTaskId(b, "task-drop");
    trackChatStream("task-keep", keep);
    trackChatStream("task-drop", drop);

    useSessionsStore.getState().deleteSession(b);

    expect(dropSpy).toHaveBeenCalled();
    expect(keepSpy).not.toHaveBeenCalled();
    abortChatStream("task-keep");
    dropProjectPark(a);
  });

  it("migrates legacy ChatSession to Project with default Space", async () => {
    const { DEFAULT_SPACE_ID } = await import("../../renderer/src/store/spaces");
    const persistApi = (useSessionsStore as unknown as {
      persist: { rehydrate: () => Promise<void> };
    }).persist;

    localStorage.setItem(
      "my-cowork-sessions",
      JSON.stringify({
        state: {
          sessions: [
            {
              id: "legacy-1",
              title: "旧聊天",
              createdAt: 1,
              updatedAt: 2,
              status: "idle",
            },
          ],
          activeId: "legacy-1",
          messagesById: {
            "legacy-1": [{ id: "m1", role: "user", content: "hello" }],
          },
        },
        version: 1,
      }),
    );

    await persistApi.rehydrate();
    const s = useSessionsStore.getState();
    expect(s.sessions[0]?.id).toBe("legacy-1");
    expect(s.sessions[0]?.spaceId).toBe(DEFAULT_SPACE_ID);
    expect(s.sessions[0]?.workdirMode).toBe("artifact-only");
    expect(s.getMessages("legacy-1")).toEqual([
      { id: "m1", role: "user", content: "hello" },
    ]);
  });

  it("createProject attaches spaceId and workdirMode", () => {
    const id = useSessionsStore.getState().createProject("folder task", {
      spaceId: "space-folder",
      workdirMode: "direct-write",
    });
    const p = useSessionsStore.getState().sessions.find((x) => x.id === id);
    expect(p?.spaceId).toBe("space-folder");
    expect(p?.workdirMode).toBe("direct-write");
  });

  it("deleteSession removes project and messages", () => {
    const a = useSessionsStore.getState().createProject("keep", {
      spaceId: "space-a",
    });
    const b = useSessionsStore.getState().createProject("drop", {
      spaceId: "space-a",
    });
    useSessionsStore.getState().saveMessages(b, [
      { id: "m1", role: "user", content: "bye" },
    ]);
    useSessionsStore.getState().setActive(b);

    useSessionsStore.getState().deleteSession(b);

    const state = useSessionsStore.getState();
    expect(state.sessions.find((x) => x.id === b)).toBeUndefined();
    expect(state.getMessages(b)).toEqual([]);
    expect(state.activeId).toBe(a);
    expect(useSessionStore.getState().messages).toEqual([]);
  });

  it("deleteSpaceCompletely removes space and its projects", async () => {
    const { useSpacesStore, DEFAULT_SPACE_ID } = await import(
      "../../renderer/src/store/spaces"
    );
    const { deleteSpaceCompletely } = await import(
      "../../renderer/src/store/sessions"
    );

    useSpacesStore.setState({
      spaces: [
        {
          id: DEFAULT_SPACE_ID,
          name: "本地工作区",
          sourceType: "blank",
          rootPath: null,
          createdAt: 1,
          updatedAt: 1,
        },
      ],
      activeSpaceId: DEFAULT_SPACE_ID,
    });

    const spaceId = useSpacesStore.getState().createBlankSpace("临时区");
    const p1 = useSessionsStore.getState().createProject("in space", {
      spaceId,
    });
    useSessionsStore.getState().createProject("also", { spaceId });
    useSessionsStore.getState().createProject("elsewhere", {
      spaceId: DEFAULT_SPACE_ID,
    });

    expect(deleteSpaceCompletely(spaceId)).toBe(true);
    expect(useSpacesStore.getState().spaces.find((s) => s.id === spaceId)).toBeUndefined();
    expect(
      useSessionsStore.getState().sessions.some((s) => s.spaceId === spaceId),
    ).toBe(false);
    expect(useSessionsStore.getState().sessions.find((s) => s.id === p1)).toBeUndefined();

    expect(useSpacesStore.getState().spaces).toHaveLength(1);
    expect(deleteSpaceCompletely(DEFAULT_SPACE_ID)).toBe(false);
  });
});
