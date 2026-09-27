// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("desktop session persistence", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it("imports existing local sessions when backend storage is empty", async () => {
    const { useSessionsStore } = await import("../../renderer/src/store/sessions");
    const { connectDesktopSessionSync } = await import("../../renderer/src/store/desktopSessionSync");
    useSessionsStore.setState({
      sessions: [{ id: "legacy", title: "旧会话", spaceId: "space-local", workdirMode: "artifact-only", createdAt: 1, updatedAt: 2, status: "done" }],
      activeId: "legacy",
      messagesById: { legacy: [{ id: "m1", role: "user", content: "旧问题" }] },
    });
    const saved: unknown[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === "PUT") {
        saved.push(JSON.parse(String(options.body)));
        return { ok: true, json: async () => ({ ok: true }) };
      }
      return { ok: true, json: async () => ({ snapshot: null }) };
    }));
    await connectDesktopSessionSync("http://127.0.0.1:8765");
    expect(saved).toHaveLength(1);
    expect((saved[0] as { sessions: Array<{ id: string }> }).sessions[0].id).toBe("legacy");
    expect((saved[0] as { spaces: Array<{ id: string }> }).spaces[0].id).toBe("space-local");
    vi.unstubAllGlobals();
  });

  it("restores backend history over stale local cache and marks interrupted runs", async () => {
    const { useSessionsStore } = await import("../../renderer/src/store/sessions");
    const { connectDesktopSessionSync } = await import("../../renderer/src/store/desktopSessionSync");
    useSessionsStore.setState({
      sessions: [{ id: "stale", title: "旧缓存", spaceId: "space-local", workdirMode: "artifact-only", createdAt: 1, updatedAt: 1, status: "done" }],
      activeId: "stale",
      messagesById: { stale: [] },
    });
    const remote = {
      sessions: [{ id: "remote", title: "最新会话", spaceId: "space-local", workdirMode: "artifact-only", createdAt: 2, updatedAt: 3, status: "running" }],
      activeId: "remote",
      messagesById: { remote: [{ id: "m2", role: "user", content: "远端记录" }] },
      spaces: [{ id: "space-local", name: "本地工作区", sourceType: "blank", rootPath: null, createdAt: 1, updatedAt: 1 }],
      activeSpaceId: "space-local",
    };
    const saved: unknown[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === "PUT") {
        saved.push(JSON.parse(String(options.body)));
        return { ok: true, json: async () => ({ ok: true }) };
      }
      return { ok: true, json: async () => ({ snapshot: remote }) };
    }));
    await connectDesktopSessionSync("http://127.0.0.1:8765");
    expect(useSessionsStore.getState().activeId).toBe("remote");
    expect(useSessionsStore.getState().getMessages("remote")[0].content).toBe("远端记录");
    expect(useSessionsStore.getState().sessions[0].status).toBe("error");
    expect(saved).toHaveLength(1);
    vi.unstubAllGlobals();
  });
});
