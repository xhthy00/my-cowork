import { describe, expect, it } from "vitest";

import {
  displayTitleFromUserContent,
  fileNameFromPath,
  parseUserAttachments,
} from "../../renderer/src/lib/userAttachments";

describe("userAttachments", () => {
  it("parses paths and strips marker from display text", () => {
    const raw =
      "帮我对这个文档提几点建议\n\n[附件: /Users/me/Documents/关于议案.docx]";
    const { text, paths } = parseUserAttachments(raw);
    expect(text).toBe("帮我对这个文档提几点建议");
    expect(paths).toEqual(["/Users/me/Documents/关于议案.docx"]);
  });

  it("supports multiple comma-separated paths", () => {
    const { paths } = parseUserAttachments(
      "[附件: /tmp/a.docx, /tmp/b.txt]",
    );
    expect(paths).toEqual(["/tmp/a.docx", "/tmp/b.txt"]);
  });

  it("fileNameFromPath returns basename", () => {
    expect(fileNameFromPath("/Users/me/Documents/关于议案.docx")).toBe(
      "关于议案.docx",
    );
  });

  it("displayTitleFromUserContent hides paths", () => {
    expect(
      displayTitleFromUserContent(
        "帮我对这个文档提几点建设性的修改建议\n\n[附件: /Users/me/长路径/文件.docx]",
      ),
    ).toBe("帮我对这个文档提几点建设性的修改建议");
    expect(
      displayTitleFromUserContent(
        "[附件: /Users/me/Documents/关于议案.docx]",
      ),
    ).toBe("关于议案.docx");
  });
});
