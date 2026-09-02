import { describe, expect, it } from "vitest";

import {
  isProcessNarration,
  looksLikeFinalAnswer,
  stripProcessNarration,
} from "../../renderer/src/lib/processNarration";

describe("processNarration", () => {
  it("treats MiniMax mid-run status talk as process", () => {
    const talk =
      "我来帮你调研扬州购房政策并给出购房建议。让我先制定计划，然后搜索最新信息。我已经获得了关键政策信息，现在让我搜索扬州房价行情。我已经获取了足够的关键信息。现在整理笔记并撰写报告。";
    expect(isProcessNarration(talk)).toBe(true);
    expect(stripProcessNarration(talk)).toBe("");
    expect(looksLikeFinalAnswer(talk)).toBe(false);
  });

  it("hides 我先梳理 / 我已经搜集 status (WorkBuddy: not the end card)", () => {
    const talk =
      "我先梳理任务、查询扬州购房政策的最新信息，然后整理成 HTML 报告。我已经搜集到足够多政策信息（2024-2026年扬州最新购房政策、房贷利率、公积金新政、人才补贴、契税等），现在整理笔记并撰写最终 HTML 报告。";
    expect(isProcessNarration(talk)).toBe(true);
    expect(looksLikeFinalAnswer(talk)).toBe(false);
  });

  it("keeps a WorkBuddy-style final report", () => {
    const report = `调研报告已生成。以下是核心要点摘要：

## 扬州现行购房政策要点

一、政策框架
扬州已取消限购。`;
    expect(looksLikeFinalAnswer(report)).toBe(true);
    expect(stripProcessNarration(report)).toContain("政策要点");
  });

  it("keeps a real report after stripping status sentences", () => {
    const mixed =
      "让我先制定计划，然后搜索最新信息。\n\n## 购房建议\n扬州已取消限购。";
    expect(isProcessNarration(mixed)).toBe(false);
    expect(looksLikeFinalAnswer(mixed)).toBe(true);
    expect(stripProcessNarration(mixed)).toContain("购房建议");
    expect(stripProcessNarration(mixed)).not.toContain("让我先制定计划");
    expect(stripProcessNarration(mixed)).toBe("## 购房建议\n扬州已取消限购。");
  });

  it("preserves markdown tables, headings, and links", () => {
    const report = `## 购房建议

| 人群 | 推荐板块 | 关键策略 |
| --- | --- | --- |
| 刚需首套 | 广陵区 | 公积金优先 |

参考：http://example.com/policy`;
    const out = stripProcessNarration(`我先梳理任务。\n\n${report}`);
    expect(out).toContain("## 购房建议");
    expect(out).toContain("| 人群 | 推荐板块 | 关键策略 |");
    expect(out).toContain("| --- | --- | --- |");
    expect(out).toContain("| 刚需首套 | 广陵区 | 公积金优先 |");
    expect(out).not.toMatch(/\|\|/);
    expect(out).toContain("http://example.com/policy");
    expect(out).not.toContain("我先梳理");
  });

  it("keeps a GFM header that omits the leading pipe", () => {
    const report = `## 操作说明

🕹️ 操作说明 | 按键 | 功能 |
|---|---|---|
| 空格 | 发射 |`;
    const out = stripProcessNarration(`我先梳理任务。\n\n${report}`);
    expect(out).toContain("🕹️ 操作说明 | 按键 | 功能 |");
    expect(out).toContain("|---|---|---|");
    expect(out).not.toMatch(/功能 \|\|---/);
  });
});
