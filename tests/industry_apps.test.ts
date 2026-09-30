import { describe, expect, it } from "vitest";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";

import { resolveAppAsset, serveAppAsset, validAppRequest } from "../electron/industry_apps";

const registry = {
  apps: {
    "cn.example.taskboard": { version: "1.0.0", enabled: true },
  },
};

describe("industry app asset resolver", () => {
  it("serves only files under the enabled application's frontend directory", () => {
    expect(resolveAppAsset(
      "mycowork-app://cn.example.taskboard/index.html",
      registry,
      "/tmp/mycowork-industry",
    )).toBe(path.resolve("/tmp/mycowork-industry/packages/cn.example.taskboard/1.0.0/frontend/dist/index.html"));
    expect(resolveAppAsset(
      "mycowork-app://cn.example.other/index.html",
      registry,
      "/tmp/mycowork-industry",
    )).toBeNull();
    expect(resolveAppAsset(
      "mycowork-app://cn.example.taskboard/%5Cprivate",
      registry,
      "/tmp/mycowork-industry",
    )).toBeNull();
  });

  it("serves installed assets with a restrictive CSP", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "mycowork-app-test-"));
    try {
      const directory = path.join(root, "packages", "cn.example.taskboard", "1.0.0", "frontend", "dist");
      fs.mkdirSync(directory, { recursive: true });
      fs.writeFileSync(path.join(directory, "index.html"), "<h1>Taskboard</h1>");
      const response = await serveAppAsset("mycowork-app://cn.example.taskboard/index.html", root, registry);
      expect(response.status).toBe(200);
      expect(await response.text()).toContain("Taskboard");
      expect(response.headers.get("Content-Security-Policy")).toContain("connect-src 'none'");
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects old-generation assets after an atomic runtime switch", () => {
    const current = { ...registry, generation: "new-runtime" };
    expect(resolveAppAsset("mycowork-app://cn.example.taskboard/old-runtime/app.js", current, os.tmpdir())).toBeNull();
    expect(resolveAppAsset("mycowork-app://cn.example.taskboard/new-runtime/app.js", current, os.tmpdir())).toContain("1.0.0");
  });
});

describe("industry app backend request", () => {
  it("keeps requests within the app's own route namespace", () => {
    expect(validAppRequest("cn.example.taskboard", "GET", "/tasks?page=1")).toBe(true);
    expect(validAppRequest("cn.example.taskboard", "GET", "/../audit")).toBe(false);
    expect(validAppRequest("cn.example.taskboard", "GET", "/%2e%2e/audit")).toBe(false);
    expect(validAppRequest("cn.example.taskboard", "GET", "//evil.test/")).toBe(false);
  });
});
