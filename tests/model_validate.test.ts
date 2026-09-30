import { describe, expect, it, vi } from "vitest";

import { lightweightValidate } from "../electron/model_validate";

describe("lightweightValidate", () => {
  it("rejects empty model id", async () => {
    const r = await lightweightValidate({
      provider: "openai_compat",
      model: "  ",
      apiKey: "sk",
    });
    expect(r.ok).toBe(false);
  });

  it("succeeds when /models returns ok", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    const r = await lightweightValidate({
      provider: "openrouter",
      model: "openai/gpt-4o-mini",
      apiKey: "sk-or",
      baseUrl: "https://openrouter.ai/api/v1",
    });
    expect(r.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
