import { describe, expect, it, vi } from "vitest";
import { IndustryLifecycle, MaintenancePipe } from "../electron/industry_lifecycle";

function harness() {
  const events: string[] = [];
  let op: any = null;
  const runtime = { generation: "new", active: 0, tasks: [], apps: [{ id: "cn.test.app", version: "2.0.0", status: "ready" }] };
  const pipe: MaintenancePipe = {
    call: vi.fn(async (request: any) => {
      events.push(request.command);
      if (request.command === "list") return { apps: [], operation: op };
      if (request.command === "begin") return op = { id: "operation", app_id: "cn.test.app", phase: "staged" };
      if (request.command === "prepare") { op.phase = "starting"; return { token: "candidate" }; }
      if (request.command === "commit") { op.phase = "committed"; return op; }
      if (request.command === "restore") { op.phase = "restoring"; return { token: "old" }; }
      if (request.command === "disable_failed") return { token: "safe" };
      if (request.command === "cancel") { op.phase = "cancelled"; return op; }
      return {};
    }) as MaintenancePipe["call"], close: vi.fn(),
  };
  const hooks = {
    pipe: () => pipe, running: () => true, modelReady: async () => true,
    start: vi.fn(async () => { events.push("start"); }),
    stop: vi.fn(async () => { events.push("stop"); }),
    runtime: vi.fn(async (action?: string) => { events.push(action || "runtime"); return runtime; }),
    publish: vi.fn(() => { events.push("publish"); }), changed: vi.fn(),
  };
  return { lifecycle: new IndustryLifecycle(hooks), hooks, events, pipe, runtime };
}

describe("industry lifecycle coordinator", () => {
  it("does not drain or restart an unchanged running development revision", async () => {
    const { lifecycle, pipe, hooks } = harness();
    (pipe.call as any).mockImplementation(async (request: any) => request.command === 'list' ? {} : { unchanged: true });
    await lifecycle.run({ action: 'develop' });
    expect(hooks.stop).not.toHaveBeenCalled();
    expect(hooks.start).not.toHaveBeenCalled();
    expect(lifecycle.status.message).toContain('内容未变');
  });
  it("coalesces identical requests while rejecting a different operation", async () => {
    const { lifecycle, hooks } = harness();
    const first = lifecycle.run({ action: "install" });
    expect(lifecycle.run({ action: "install" })).toBe(first);
    await expect(lifecycle.run({ action: "disable" })).rejects.toThrow("已有应用操作");
    await first;
    expect(hooks.start).toHaveBeenCalledTimes(1);
  });

  it("drains and stops an existing runtime when its last model is removed", async () => {
    const { lifecycle, hooks, events } = harness();
    hooks.modelReady = async () => false;
    await lifecycle.run({ action: "restart" });
    expect(events.indexOf("drain")).toBeLessThan(events.indexOf("stop"));
    expect(events).toContain("cancel");
    expect(hooks.start).not.toHaveBeenCalled();
    expect(lifecycle.status.phase).toBe("pending_activation");
  });

  it("drains, stops, prepares, checks and commits before publishing", async () => {
    const { lifecycle, events } = harness();
    await lifecycle.run({ action: "install" });
    expect(events.indexOf("drain")).toBeLessThan(events.indexOf("stop"));
    expect(events.indexOf("stop")).toBeLessThan(events.indexOf("prepare"));
    expect(events.indexOf("prepare")).toBeLessThan(events.indexOf("start"));
    expect(events.indexOf("runtime")).toBeLessThan(events.indexOf("commit"));
    expect(events.indexOf("commit")).toBeLessThan(events.lastIndexOf("publish"));
    expect(lifecycle.status.phase).toBe("committed");
  });

  it("disables a broken committed app on restart without rolling data back", async () => {
    const { lifecycle, hooks, events, runtime } = harness();
    hooks.runtime.mockImplementation(async action => {
      if (!action && hooks.start.mock.calls.length === 1) return { ...runtime, apps: [{ id: "cn.test.app", version: "2.0.0", status: "load_failed", error: "broken" }] };
      return runtime;
    });
    await lifecycle.run({ action: "restart" });
    expect(events).toContain("disable_failed");
    expect(events).not.toContain("restore");
    expect(hooks.start).toHaveBeenCalledTimes(2);
    expect(lifecycle.status.phase).toBe("committed");
  });

  it("cancels waiting without stopping existing work", async () => {
    const { lifecycle, hooks, events } = harness();
    hooks.runtime.mockImplementation(async () => {
      lifecycle.cancel();
      return { generation: "old", active: 1, tasks: ["task"], apps: [] };
    });
    await lifecycle.run({ action: "install" });
    expect(events).toContain("cancel");
    expect(hooks.stop).not.toHaveBeenCalled();
    expect(lifecycle.status.phase).toBe("cancelled");
  });

  it("leaves active work alone when ZIP validation fails before begin", async () => {
    const { lifecycle, pipe, hooks, events } = harness();
    const original = pipe.call.bind(pipe);
    pipe.call = async request => {
      if (request.command === "begin") throw new Error("invalid ZIP");
      return original(request);
    };
    await lifecycle.run({ action: "install" });
    expect(hooks.stop).not.toHaveBeenCalled();
    expect(events).not.toContain("restore");
    expect(lifecycle.status.phase).toBe("failed");
  });

  it("restores after failed candidate startup, then validates old runtime", async () => {
    const { lifecycle, hooks, events } = harness();
    hooks.start.mockRejectedValueOnce(new Error("health failure"));
    await lifecycle.run({ action: "install" });
    expect(events).toContain("restore");
    expect(hooks.start).toHaveBeenCalledTimes(2);
    expect(lifecycle.status.phase).toBe("restored");
  });

  it("never restores data after commit, even when opening the runtime fails", async () => {
    const { lifecycle, hooks, events, runtime } = harness();
    hooks.runtime.mockImplementation(async action => {
      if (action === "open") throw new Error("pipe disconnected");
      return runtime;
    });
    await lifecycle.run({ action: "install" });
    expect(events).toContain("commit");
    expect(events).not.toContain("restore");
    expect(lifecycle.status.phase).toBe("recovery_required");
  });

  it("does not back up data if process exit cannot be confirmed", async () => {
    const { lifecycle, hooks, events } = harness();
    hooks.stop.mockRejectedValueOnce(new Error("still running"));
    await lifecycle.run({ action: "install" });
    expect(events).not.toContain("prepare");
    expect(events).not.toContain("restore");
    expect(lifecycle.status.phase).toBe("failed");
  });
});
