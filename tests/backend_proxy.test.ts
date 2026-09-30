import { afterEach, describe, expect, it, vi } from "vitest";
import { BackendProxy } from "../electron/backend_proxy";

afterEach(() => vi.unstubAllGlobals());

describe("host backend transport", () => {
  const make = () => new BackendProxy(() => "http://127.0.0.1:8123", () => "private-token");

  it("only forwards requests to the current backend without following redirects", async () => {
    const fetch = vi.fn(async (_url, init) => {
      expect(init.headers.get("X-MyCowork-Industry-Token")).toBe("private-token");
      expect(init.redirect).toBe("error");
      return new Response("ok");
    });
    vi.stubGlobal("fetch", fetch);
    const proxy = make();
    for (const url of ["https://example.com/api/chat", "http://127.0.0.1:9999/api/chat", "http://user@127.0.0.1:8123/api/chat"]) {
      await expect(proxy.request(1, "bad", { url })).rejects.toThrow();
    }
    expect(fetch).not.toHaveBeenCalled();
    await proxy.request(1, "own", { url: "http://127.0.0.1:8123/api/chat", method: "POST", body: new TextEncoder().encode("{}") });
    proxy.cancel(1, "own");
  });

  it("streams bytes on demand and restricts reads to the requesting window", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("data: 中文\n\n", { headers: { "Content-Type": "text/event-stream" } })));
    const proxy = make();
    const response = await proxy.request(7, "stream", { url: "http://127.0.0.1:8123/api/chat" });
    expect(response.status).toBe(200);
    await expect(proxy.read(8, "stream")).rejects.toThrow();
    expect(new TextDecoder().decode((await proxy.read(7, "stream")).value)).toBe("data: 中文\n\n");
    expect((await proxy.read(7, "stream")).done).toBe(true);
    await expect(proxy.read(7, "stream")).rejects.toThrow();
  });

  it("cancels pending network work when its owner aborts or closes", async () => {
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
    })));
    const proxy = make();
    const pending = proxy.request(3, "pending", { url: "http://127.0.0.1:8123/api/chat" });
    const assertion = expect(pending).rejects.toThrow("aborted");
    expect(() => proxy.cancel(4, "pending")).toThrow();
    proxy.closeOwner(3);
    await assertion;
  });
});
