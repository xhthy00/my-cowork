import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { describe, expect, it } from "vitest";

import {
  getActiveProfile,
  initModelsStore,
  loadModels,
  removeProfile,
  setActiveId,
  upsertProfile,
} from "../electron/models_store";

describe("models_store", () => {
  it("persists upsert/setActive/remove", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-models-"));
    initModelsStore(dir);

    const a = upsertProfile({
      id: "a",
      name: "Claude",
      provider: "anthropic",
      model: "claude-sonnet-4-20250514",
    });
    expect(a.activeId).toBe("a");
    expect(getActiveProfile()?.name).toBe("Claude");

    upsertProfile({
      id: "b",
      name: "GPT",
      provider: "openai_compat",
      model: "gpt-4o-mini",
      baseUrl: "https://api.openai.com/v1",
    });
    setActiveId("b");
    expect(loadModels().activeId).toBe("b");
    expect(getActiveProfile()?.model).toBe("gpt-4o-mini");

    const after = removeProfile("b");
    expect(after.activeId).toBe("a");
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("stores validation metadata and presetId", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "my-cowork-models-meta-"));
    initModelsStore(dir);
    upsertProfile({
      id: "or",
      name: "OpenRouter",
      provider: "openrouter",
      model: "openai/gpt-4o-mini",
      baseUrl: "https://openrouter.ai/api/v1",
      isValid: true,
      lastValidatedAt: "2026-01-01T00:00:00.000Z",
      category: "cloud_byok",
      presetId: "openrouter",
    });
    const p = getActiveProfile();
    expect(p?.presetId).toBe("openrouter");
    expect(p?.isValid).toBe(true);
    expect(p?.category).toBe("cloud_byok");
    fs.rmSync(dir, { recursive: true, force: true });
  });
});
