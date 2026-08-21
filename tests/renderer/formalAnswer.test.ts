/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import {
  endCardFromContent,
  formalAnswerFromContent,
  isWorkforceProcessMeta,
  resolveEndMessageText,
  streamingAnswerFromRaw,
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

  it("end card prefers summary and text after the last think", () => {
    const text = `<think>planning</think>
我先检索扬州限购。
<think>more</think>
<summary>## 结论
扬州已取消限购。
</summary>`;
    expect(endCardFromContent(text)).toContain("扬州已取消限购");
    expect(endCardFromContent(text)).not.toContain("我先检索");
    expect(endCardFromContent(text)).not.toContain("planning");
  });

  it("strips MiniMax orphaned closing think before the answer", () => {
    const text = "内部推理一大段\n</think>\n扬州已取消限购。";
    expect(formalAnswerFromContent(text)).toBe("扬州已取消限购。");
  });

  it("hides mid-run status talk so only the final answer remains", () => {
    const talk =
      "我来帮你调研扬州购房政策并给出购房建议。让我先制定计划，然后搜索最新信息。我已经获得了关键政策信息，现在让我搜索扬州房价行情。我已经获取了足够的关键信息。现在整理笔记并撰写报告。";
    expect(formalAnswerFromContent(talk)).toBe("");
    const mixed = `${talk}\n\n## 购房建议\n扬州已取消限购。`;
    expect(formalAnswerFromContent(mixed)).toContain("购房建议");
    expect(formalAnswerFromContent(mixed)).toContain("扬州已取消限购");
    expect(formalAnswerFromContent(mixed)).not.toContain("让我先制定计划");
  });
});

describe("resolveEndMessageText (Eigent END card)", () => {
  it("prefers <summary> and otherwise keeps markdown", () => {
    expect(
      resolveEndMessageText("<think>x</think>\n<summary>## 结论\n已完成</summary>"),
    ).toBe("## 结论\n已完成");
    const report = `## 购房建议

| 人群 | 推荐板块 |
| --- | --- |
| 刚需首套 | 广陵区 |`;
    expect(resolveEndMessageText(report)).toContain("| 人群 | 推荐板块 |");
    expect(resolveEndMessageText(report)).not.toMatch(/\|\|/);
  });

  it("drops process-only payloads instead of showing them as the card", () => {
    expect(
      resolveEndMessageText("我先梳理任务、查询扬州购房政策的最新信息。"),
    ).toBe("");
  });
});

describe("end card vs process talk", () => {
  it("drops MiniMax process narration from the formal answer", () => {
    const talk =
      "我先梳理任务、查询扬州购房政策的最新信息，然后整理成 HTML 报告。";
    expect(formalAnswerFromContent(talk)).toBe("");
    expect(endCardFromContent(talk)).toBe("");
  });

  it("keeps a markdown report as the end card", () => {
    const report = `## 扬州现行购房政策要点

扬州已取消限购。`;
    expect(formalAnswerFromContent(report)).toContain("扬州已取消限购");
    expect(endCardFromContent(report)).toContain("扬州已取消限购");
  });

  it("does not collapse markdown tables in the end card", () => {
    const report = `## 购房建议

| 人群 | 推荐板块 |
| --- | --- |
| 刚需首套 | 广陵区 |`;
    const out = formalAnswerFromContent(report);
    expect(out).toContain("| 人群 | 推荐板块 |");
    expect(out).toContain("| --- | --- |");
    expect(out).not.toMatch(/\|\|/);
    expect(endCardFromContent(report)).toContain("| 刚需首套 | 广陵区 |");
  });
});

describe("streamingAnswerFromRaw", () => {
  it("hides think and streams the answer after </think>", () => {
    expect(streamingAnswerFromRaw("<think>The user is asking</think>")).toBe("");
    expect(
      streamingAnswerFromRaw("<think>The user is asking</think>\n扬州已取消限购。"),
    ).toBe("扬州已取消限购。");
  });

  it("does not leak MiniMax reasoning before </think>", () => {
    expect(
      streamingAnswerFromRaw("The user is asking me to research Yangzhou policies in detail."),
    ).toBe("");
  });

  it("starts untagged buffers at the first markdown heading", () => {
    const raw = `Let me gather sources first.

## 购房建议

扬州已取消限购。`;
    expect(streamingAnswerFromRaw(raw)).toBe("## 购房建议\n\n扬州已取消限购。");
  });
});
