import { describe, expect, it } from "vitest";
import * as path from "path";

import { isFsPathInside, isLocalfileAllowed, localfileUrlToFsPath } from "../electron/localfile";
import { toFileUrl } from "../renderer/src/store/preview";

describe("localfileUrlToFsPath (win32)", () => {
  it("maps Chromium hostname-drive URLs to C:\\Users\\...", () => {
    const resolved = localfileUrlToFsPath(
      "localfile://c/Users/xhthy/.my-cowork/spaces/s1/report.html",
      "win32",
    );
    expect(resolved).toBe(
      path.win32.resolve("C:\\Users\\xhthy\\.my-cowork\\spaces\\s1\\report.html"),
    );
  });

  it("maps localfile:///C:/Users/... (colon in pathname)", () => {
    const resolved = localfileUrlToFsPath(
      "localfile:///C:/Users/xhthy/.my-cowork/spaces/s1/report.html",
      "win32",
    );
    expect(resolved).toBe(
      path.win32.resolve("C:\\Users\\xhthy\\.my-cowork\\spaces\\s1\\report.html"),
    );
  });

  it("decodes percent-encoded Chinese filenames", () => {
    const name = encodeURIComponent("评估报告.html");
    const resolved = localfileUrlToFsPath(
      `localfile://c/Users/xhthy/.my-cowork/spaces/s1/${name}`,
      "win32",
    );
    expect(resolved.toLowerCase()).toContain("评估报告.html".toLowerCase());
  });
});

describe("isFsPathInside (win32 drive-letter case)", () => {
  it("allows a file under homedir even when drive letters differ in case", () => {
    const file = localfileUrlToFsPath(
      "localfile://c/Users/xhthy/.my-cowork/spaces/s1/a.html",
      "win32",
    );
    expect(isFsPathInside(file, "C:\\Users\\xhthy", "win32")).toBe(true);
    expect(
      isLocalfileAllowed(file, ["C:\\Users\\xhthy", "C:\\Temp"], "win32"),
    ).toBe(true);
  });

  it("rejects paths outside the allow-list", () => {
    expect(
      isFsPathInside("C:\\Windows\\notepad.exe", "C:\\Users\\xhthy", "win32"),
    ).toBe(false);
  });

  it("rejects parent traversal", () => {
    expect(
      isFsPathInside("C:\\Users\\xhthy\\..\\Windows\\a.html", "C:\\Users\\xhthy", "win32"),
    ).toBe(false);
  });
});

describe("toFileUrl round-trip (win32)", () => {
  it("keeps the preview URL inside homedir after Chromium-style rewrite", () => {
    const original = "C:\\Users\\xhthy\\.my-cowork\\spaces\\s1\\评估报告.html";
    const url = toFileUrl(original);
    expect(url.startsWith("localfile://")).toBe(true);
    // Chromium rewrites localfile:///C:/Users → localfile://c/Users
    const rewritten = url.replace(/^localfile:\/\/\/C:/i, "localfile://c");
    const resolved = localfileUrlToFsPath(rewritten, "win32");
    expect(isFsPathInside(resolved, "C:\\Users\\xhthy", "win32")).toBe(true);
    expect(resolved.toLowerCase()).toContain("评估报告.html".toLowerCase());
  });
});

describe("localfileUrlToFsPath (darwin)", () => {
  it("restores /Users hostname casing", () => {
    const resolved = localfileUrlToFsPath(
      "localfile://users/tanghaoyu/Desktop/a.html",
      "darwin",
    );
    expect(resolved).toBe("/Users/tanghaoyu/Desktop/a.html");
  });
});
