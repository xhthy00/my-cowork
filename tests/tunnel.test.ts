import { EventEmitter } from "events";
import { afterEach, describe, expect, it, vi } from "vitest";

import { startTunnel, type SpawnFn } from "../electron/tunnel";

class FakeChild extends EventEmitter {
  stdout = new EventEmitter();
  stderr = new EventEmitter();
  kill = vi.fn();
}

describe("startTunnel", () => {
  let child: FakeChild;

  afterEach(() => {
    vi.useRealTimers();
  });

  it("resolves public URL from cloudflared stdout", async () => {
    child = new FakeChild();
    const spawnFn: SpawnFn = vi.fn(() => child as never);

    const pending = startTunnel("http://127.0.0.1:8765", spawnFn, 5_000);
    child.stdout.emit(
      "data",
      Buffer.from("INF Running tunnel https://random-words-1234.trycloudflare.com\n"),
    );

    const handle = await pending;
    expect(handle.url).toBe("https://random-words-1234.trycloudflare.com");
    handle.stop();
    expect(child.kill).toHaveBeenCalled();
  });

  it("reads URL from stderr (cloudflared often logs there)", async () => {
    child = new FakeChild();
    const spawnFn: SpawnFn = vi.fn(() => child as never);

    const pending = startTunnel("http://127.0.0.1:8765", spawnFn, 5_000);
    child.stderr.emit(
      "data",
      Buffer.from("|  https://abc-def.trycloudflare.com                                |\n"),
    );

    const handle = await pending;
    expect(handle.url).toBe("https://abc-def.trycloudflare.com");
    handle.stop();
  });

  it("maps spawn ENOENT to an install hint", async () => {
    child = new FakeChild();
    const spawnFn: SpawnFn = vi.fn(() => {
      queueMicrotask(() => {
        child.emit("error", Object.assign(new Error("spawn cloudflared ENOENT"), { code: "ENOENT" }));
      });
      return child as never;
    });

    await expect(startTunnel("http://127.0.0.1:8765", spawnFn, 5_000)).rejects.toThrow(
      /未找到 cloudflared/,
    );
  });
});
