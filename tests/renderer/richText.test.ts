/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import {
  segmentsToHtml,
  tokenizeRichPlainText,
} from "../../renderer/src/lib/richText";

describe("richText", () => {
  it("tokenizes #skill and @connector as chips", () => {
    expect(tokenizeRichPlainText("用 #weekly-report 和 @github 完成")).toEqual([
      { type: "text", text: "用 " },
      { type: "skill", text: "#weekly-report" },
      { type: "text", text: " 和 " },
      { type: "connector", text: "@github" },
      { type: "text", text: " 完成" },
    ]);
  });

  it("renders skill chips as non-editable highlighted spans", () => {
    const html = segmentsToHtml(tokenizeRichPlainText("#my-skill"));
    expect(html).toContain('data-rich-skill="1"');
    expect(html).toContain('contenteditable="false"');
    expect(html).toContain("#my-skill");
    expect(html).toMatch(/text-ds-text-(success|warning|terminal|document)-default-default/);
  });

  it("tokenizes @connector and URL in a sent-style user message", () => {
    const segs = tokenizeRichPlainText(
      "@fetch 帮我获取该网页内容形成md文档，https://www.jianshu.com/p/ccb88e69c3c6",
    );
    expect(segs[0]).toEqual({ type: "connector", text: "@fetch" });
    expect(segs.some((s) => s.type === "url" && s.text.includes("jianshu.com"))).toBe(
      true,
    );
  });
});
