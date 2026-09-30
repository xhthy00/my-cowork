import { afterEach, expect, it, vi } from "vitest";
import { apiFetch } from "../renderer/src/api/backend";

afterEach(() => vi.unstubAllGlobals());

it("uses the host transport for JSON bodies and streamed responses without a token", async () => {
  const backendRequest = vi.fn().mockResolvedValue({ status: 200, statusText: "OK", headers: { "content-type": "application/json" } });
  const backendRead = vi.fn().mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('{"answer":"已保存"}') }).mockResolvedValueOnce({ done: true });
  vi.stubGlobal("window", { api: { backendRequest, backendRead, backendCancel: vi.fn().mockResolvedValue(undefined) } });
  const response = await apiFetch("http://127.0.0.1:9000/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "你好" }) });
  expect(await response.json()).toEqual({ answer: "已保存" });
  const request = backendRequest.mock.calls[0][1];
  expect(request.headers).toEqual({ "content-type": "application/json" });
  expect(JSON.parse(new TextDecoder().decode(request.body))).toEqual({ text: "你好" });
});

it("propagates abort and preserves HTTP error status", async () => {
  const backendCancel = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("window", { api: {
    backendRequest: vi.fn().mockResolvedValue({ status: 403, statusText: "Forbidden", headers: {} }),
    backendRead: vi.fn().mockResolvedValue({ done: true }), backendCancel,
  } });
  const response = await apiFetch("http://127.0.0.1:9000/api/chat");
  expect(response.ok).toBe(false);
  expect(response.status).toBe(403);
  await response.body!.cancel();
  expect(backendCancel).toHaveBeenCalled();
  const controller = new AbortController(); controller.abort();
  await expect(apiFetch("http://127.0.0.1:9000/api/chat", { signal: controller.signal })).rejects.toHaveProperty("name", "AbortError");
});
