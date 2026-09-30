import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { initModelsStore, loadModels } from "../electron/models_store";
import { saveModelConnection } from "../electron/model_runtime";
import { getKey, setKey, deleteKey } from "../electron/keychain";

vi.mock("../electron/keychain", () => ({ getKey: vi.fn(), setKey: vi.fn(), deleteKey: vi.fn() }));
let dir: string;
const connection = { id: "c", name: "Connection", provider: "openai_compat" as const };
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), "model-runtime-"));
  initModelsStore(dir);
  vi.mocked(getKey).mockResolvedValue("old-key");
  vi.mocked(setKey).mockResolvedValue(undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  fs.rmSync(dir, { recursive: true, force: true });
});

it("rejects invalid connection edits before touching the existing credential", async () => {
  await saveModelConnection(connection);
  await expect(saveModelConnection({ ...connection, name: "", apiKey: "new-key" })).rejects.toThrow();
  await expect(saveModelConnection({ ...connection, baseUrl: "file:///invalid", apiKey: "new-key" })).rejects.toThrow();
  expect(setKey).not.toHaveBeenCalled();
  expect(loadModels().connections?.[0].name).toBe("Connection");
});

it("restores the previous key if writing the connection fails", async () => {
  await saveModelConnection(connection);
  // A directory at the atomic temporary path reproduces a failed settings write.
  fs.mkdirSync(path.join(dir, "models.json.tmp"));
  await expect(saveModelConnection({ ...connection, name: "changed", apiKey: "new-key" })).rejects.toThrow();
  expect(vi.mocked(setKey).mock.calls.map(call => call[2])).toEqual(["new-key", "old-key"]);
  expect(deleteKey).not.toHaveBeenCalled();
  expect(loadModels().connections?.[0].name).toBe("Connection");
});
