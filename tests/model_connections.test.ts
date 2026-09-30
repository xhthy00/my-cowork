import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { initModelsStore, loadModels, upsertConnection, upsertProfile, removeConnection, removeProfile } from "../electron/models_store";

let dir: string;
beforeEach(() => { dir = fs.mkdtempSync(path.join(os.tmpdir(), "model-connections-")); initModelsStore(dir); });
afterEach(() => fs.rmSync(dir, { recursive: true, force: true }));

describe("provider connections", () => {
  it("migrates same-host legacy profiles separately without moving their credentials", () => {
    fs.writeFileSync(path.join(dir, "models.json"), JSON.stringify({ activeId: "b", profiles: [
      { id: "a", name: "one", provider: "openai_compat", model: "m1", baseUrl: "https://example.com" },
      { id: "b", name: "two", provider: "openai_compat", model: "m2", baseUrl: "https://example.com" },
    ] }));
    const state = loadModels();
    expect(state.connections).toHaveLength(2);
    expect(state.connections?.map(c => c.keyAccount)).toEqual(["model:a", "model:b"]);
    expect(state.activeId).toBe("b");
    expect(loadModels()).toEqual(state);
  });
  it("shares connection edits without changing the default or other connections", () => {
    upsertConnection({ id: "c", name: "official", provider: "openai_compat", baseUrl: "https://first.example/v1" });
    upsertProfile({ id: "a", name: "A", model: "m1", provider: "openai_compat", connectionId: "c" });
    upsertProfile({ id: "b", name: "B", model: "m2", provider: "openai_compat", connectionId: "c" });
    const state = upsertConnection({ id: "c", name: "official", provider: "openai_compat", baseUrl: "https://second.example/v1" });
    expect(state.profiles.map(p => p.baseUrl)).toEqual(["https://second.example/v1", "https://second.example/v1"]);
    expect(state.activeId).toBe("a");
    expect(removeProfile("b").connections).toHaveLength(1);
    expect(removeConnection("c").profiles).toEqual([]);
  });
  it("refuses to overwrite malformed saved settings", () => {
    fs.writeFileSync(path.join(dir, "models.json"), "{broken");
    expect(() => upsertConnection({ id: "c", name: "C", provider: "openai_compat" })).toThrow();
    expect(fs.readFileSync(path.join(dir, "models.json"), "utf8")).toBe("{broken");
  });
});
