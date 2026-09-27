/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from "vitest";

import { migrateLegacyMemorySetting } from "../../renderer/src/lib/memorySettingsMigration";

describe("legacy memory setting migration", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    localStorage.removeItem("my-cowork-memory-on");
    localStorage.removeItem("my-cowork-memory-setting-migrated");
  });

  it("moves a disabled browser setting to persistent backend settings once", async () => {
    localStorage.setItem("my-cowork-memory-on", "0");
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true }) as typeof fetch;
    await migrateLegacyMemorySetting("http://127.0.0.1:8000");
    await migrateLegacyMemorySetting("http://127.0.0.1:8000");
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/memory/settings",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ enabled: false }) }),
    );
  });
});
