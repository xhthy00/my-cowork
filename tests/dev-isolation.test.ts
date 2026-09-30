import * as os from "os";
import * as path from "path";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("electron", () => ({ app: { isPackaged: false } }));

import { getAppHome, getUserTerminalBasePath } from "../electron/terminal_venv";

afterEach(() => vi.unstubAllEnvs());

describe("development data isolation", () => {
  it("keeps terminal environments inside the configured backend data directory", () => {
    const isolated = path.resolve(".cache/dev/backend");
    vi.stubEnv("MY_COWORK_DATA_DIR", isolated);
    expect(getAppHome()).toBe(isolated);
    expect(getUserTerminalBasePath("0.1.1")).toBe(path.join(isolated, "venvs", "terminal_base-0.1.1"));
  });

  it("preserves the default data directory without an override", () => {
    vi.stubEnv("MY_COWORK_DATA_DIR", "");
    expect(getAppHome()).toBe(path.join(os.homedir(), ".my-cowork"));
  });
});
