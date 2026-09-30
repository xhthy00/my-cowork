import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getModelCatalog, initModelCatalog, refreshModelCatalog } from "../electron/model_catalog";
import { initModelsStore } from "../electron/models_store";
let dir: string;
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), "model-catalog-"));
  initModelCatalog(dir);
  initModelsStore(dir);
});
afterEach(() => { vi.unstubAllGlobals(); fs.rmSync(dir, { recursive: true, force: true }); });

it("falls back to the bundled snapshot when cached entries are malformed", () => {
  fs.writeFileSync(path.join(dir, "model-catalog.json"), JSON.stringify({ updatedAt: "broken", models: [{ id: "bad", options: null }] }));
  expect(getModelCatalog().models.length).toBeGreaterThan(100);
  expect(getModelCatalog().updatedAt).not.toBe("broken");
});

it("preserves the previous snapshot on a malformed upstream option", async () => {
  const cached = JSON.stringify(getModelCatalog());
  fs.writeFileSync(path.join(dir, "model-catalog.json"), cached);
  const models = Object.fromEntries(Array.from({ length: 100 }, (_, i) => [`m${i}`, {
    name: "Model", tool_call: true, modalities: { output: ["text"] }, limit: { context: 32000, output: 8192 },
    reasoning: true, reasoning_options: [{ type: "effort", values: ["low", 3] }],
  }]));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ test: { models } }) }));
  await expect(refreshModelCatalog()).rejects.toThrow();
  expect(fs.readFileSync(path.join(dir, "model-catalog.json"), "utf8")).toBe(cached);
});
