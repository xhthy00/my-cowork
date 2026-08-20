/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import {
  formalAnswerFromContent,
  isWorkforceProcessMeta,
} from "../../renderer/src/store/session";

describe("workforce formal answer", () => {
  it("treats Subtask completed / Deliverable as process meta", () => {
    const text = `Subtask completed. Deliverable:
- /Users/me/out/report.md (1200 chars)`;
    expect(isWorkforceProcessMeta(text)).toBe(true);
    expect(formalAnswerFromContent(text)).toBe("");
  });

  it("prefers <summary> body as formal answer", () => {
    const text = `<think>planning</think>
Subtask completed.
<summary>
## 核心结论
OpenClaw 是一站式部署方案。
</summary>`;
    expect(formalAnswerFromContent(text)).toContain("核心结论");
    expect(formalAnswerFromContent(text)).not.toContain("Subtask");
  });

  it("keeps Chinese markdown answers", () => {
    const text = `## 解读报告\n\n- 产品形态：SaaS\n- 输出：~/Desktop/a.md`;
    expect(formalAnswerFromContent(text)).toContain("解读报告");
  });

  it("strips tool-calling filler", () => {
    const text = "扬州已放宽限购。正在调用工具...";
    expect(formalAnswerFromContent(text)).toContain("扬州已放宽限购");
    expect(formalAnswerFromContent(text)).not.toContain("正在调用工具");
  });

  it("drops officecli process tail after a research answer", () => {
    const text = `扬州目前已全面取消限购、限售。

Now let me set up page layout and build the cover page.

已完成。Word 版调研报告已写入：
交付摘要
文件规格：15 KB`;
    expect(formalAnswerFromContent(text)).toContain("取消限购");
    expect(formalAnswerFromContent(text)).not.toContain("page layout");
    expect(formalAnswerFromContent(text)).not.toContain("交付摘要");
  });
});
