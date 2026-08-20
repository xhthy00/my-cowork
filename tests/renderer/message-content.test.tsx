/**
 * @vitest-environment jsdom
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MessageContent, {
  collectThinkSegments,
  hasVisibleAnswer,
  normalizeMarkdown,
  normalizeMarkdownTables,
  parseContentSegments,
  parseThinkBlocks,
} from "../../renderer/src/components/chat/MessageContent";

describe("parseContentSegments", () => {
  it("keeps think and answer interleaved in document order", () => {
    const raw = [
      "<think>",
      "plan A",
      "</think>",
      "先读表。",
      "<think>",
      "plan B",
      "</think>",
      "再写报告。",
    ].join("\n");
    expect(parseContentSegments(raw)).toEqual([
      { type: "think", text: "plan A", closed: true },
      { type: "answer", text: "先读表。" },
      { type: "think", text: "plan B", closed: true },
      { type: "answer", text: "再写报告。" },
    ]);
  });

  it("handles unclosed think at the end", () => {
    expect(parseContentSegments("前言\n<think>\nstill thinking")).toEqual([
      { type: "answer", text: "前言" },
      { type: "think", text: "still thinking", closed: false },
    ]);
  });

  it("returns plain text as a single answer", () => {
    expect(parseContentSegments("普通回复")).toEqual([
      { type: "answer", text: "普通回复" },
    ]);
  });

  it("strips unsolicited officecli Word plans from think", () => {
    const raw = [
      "<think>",
      "先核对公积金和限购口径。",
      "我来用 officecli 生成正式的 Word 文档。",
      "接着把结论写入 Markdown。",
      "</think>",
      "扬州已取消限购。",
    ].join("\n");
    const segs = parseContentSegments(raw);
    const think = segs.find((s) => s.type === "think");
    expect(think?.text).toContain("公积金");
    expect(think?.text).toContain("Markdown");
    expect(think?.text).not.toContain("officecli");
    expect(think?.text).not.toContain("Word");
  });

  it("drops a think block that is only an officecli Word plan", () => {
    const raw = "<think>我来用 officecli 生成正式的 Word 文档。</think>\n扬州已取消限购。";
    const segs = parseContentSegments(raw);
    expect(segs.some((s) => s.type === "think")).toBe(false);
    expect(segs.some((s) => s.type === "answer" && s.text.includes("取消限购"))).toBe(
      true,
    );
  });
});

describe("parseThinkBlocks", () => {
  it("extracts think and keeps the answer", () => {
    const raw =
      "收到，正在处理…\n<think>\nI should call file_worker.\n</think>\n已写好 hello.txt。";
    const parsed = parseThinkBlocks(raw);
    expect(parsed.thinks).toEqual([
      { text: "I should call file_worker.", closed: true },
    ]);
    expect(parsed.answer).toContain("收到，正在处理");
    expect(parsed.answer).toContain("已写好 hello.txt");
    expect(parsed.answer).not.toContain("<think>");
  });
});

describe("collectThinkSegments / hasVisibleAnswer", () => {
  it("collects every think block", () => {
    const raw = "<think>a</think>中间<think>b</think>";
    expect(collectThinkSegments(raw)).toEqual([
      { type: "think", text: "a", closed: true },
      { type: "think", text: "b", closed: true },
    ]);
  });

  it("detects visible answers and ignores think-only content", () => {
    expect(hasVisibleAnswer("<think>only</think>")).toBe(false);
    expect(hasVisibleAnswer("<think>plan</think>\n最终答案")).toBe(true);
  });
});

describe("MessageContent deep think UI", () => {
  it("shows open summary while think tag is unclosed", () => {
    const content = ["<think>", "planning next tool"].join("\n");
    render(
      <MessageContent content={content} role="assistant" streaming />,
    );
    const details = document.querySelector("details.deep-think");
    expect(details).toBeTruthy();
    expect(details?.hasAttribute("open")).toBe(true);
    expect(screen.getByText("思考中…")).toBeInTheDocument();
    expect(details?.textContent).toMatch(/planning next tool/);
  });

  it("collapses a closed think to 深度思考", () => {
    const content = ["<think>", "done thinking", "</think>", "最终答案"].join("\n");
    render(<MessageContent content={content} role="assistant" />);
    const details = document.querySelectorAll("details.deep-think");
    expect(details).toHaveLength(1);
    expect(details[0]?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("深度思考")).toBeInTheDocument();
    expect(screen.getByText(/最终答案/)).toBeInTheDocument();
  });

  it("merges multiple thinks into one V1 summary", () => {
    const content = [
      "<think>",
      "step1",
      "</think>",
      "回答一",
      "<think>",
      "step2",
      "</think>",
      "回答二",
    ].join("\n");
    const { container } = render(
      <MessageContent content={content} role="assistant" />,
    );
    const details = document.querySelectorAll("details.deep-think");
    expect(details).toHaveLength(1);
    expect(screen.getByText("已思考 · 2 步")).toBeInTheDocument();
    expect(screen.queryAllByText("深度思考")).toHaveLength(0);
    expect(details[0]?.textContent).toMatch(/step1/);
    expect(details[0]?.textContent).toMatch(/step2/);
    const kids = Array.from(container.firstElementChild?.children ?? []);
    expect(kids[0]?.classList.contains("deep-think")).toBe(true);
    expect(kids.map((el) => el.textContent).join("")).toMatch(/回答一/);
    expect(kids.map((el) => el.textContent).join("")).toMatch(/回答二/);
  });

  it("hides think UI when hideThink is set", () => {
    const content = ["<think>", "secret", "</think>", "可见答案"].join("\n");
    render(
      <MessageContent content={content} role="assistant" hideThink />,
    );
    expect(document.querySelector("details.deep-think")).toBeNull();
    expect(screen.queryByText("深度思考")).not.toBeInTheDocument();
    expect(screen.queryByText("已思考")).not.toBeInTheDocument();
    expect(screen.getByText(/可见答案/)).toBeInTheDocument();
  });
});

describe("normalizeMarkdown", () => {
  it("breaks ATX headings glued to the previous sentence", () => {
    const raw =
      "约定价格调整机制### 2. 知识产权与代码归属- 合同中应明确权属。可用于其他客户项目### 3. 风险与责任边界";
    const out = normalizeMarkdown(raw);
    expect(out).toContain("机制\n\n### 2. 知识产权与代码归属");
    expect(out).toContain("项目\n\n### 3. 风险与责任边界");
    expect(out).toContain("归属\n- 合同中应明确权属");
    expect(out).not.toContain("机制###");
    expect(out).not.toContain("项目###");
  });

  it("does not split C# or issue hashes", () => {
    expect(normalizeMarkdown("Use C# 12 and see #123.")).toBe(
      "Use C# 12 and see #123.",
    );
  });

  it("leaves fenced code alone", () => {
    const raw = "见下：\n```\nfoo### not a heading\n```";
    expect(normalizeMarkdown(raw)).toBe(raw);
  });

  it("inserts a blank line before a flush table", () => {
    const raw =
      "说明如下：\n| # | 文件 |\n|---|------|\n| 1 | a.docx |";
    const out = normalizeMarkdownTables(raw);
    expect(out).toContain("说明如下：\n\n| # | 文件 |");
  });

  it("leaves already-spaced tables alone", () => {
    const raw = "说明\n\n| a |\n|---|\n| 1 |";
    expect(normalizeMarkdownTables(raw)).toBe(raw);
  });

  it("peels a numbered title off a glued table header", () => {
    const raw = [
      '1. 三个"硬骨头"必须有解决方案 | 技术难点 | 外包队伍应对策略 |',
      "|---|---|",
      "| 北斗协议栈 | ①团队内培养 1 名专责 |",
      "| 时空 DSL 设计 | 不能直接用 ES DSL 了事 |",
    ].join("\n");
    const out = normalizeMarkdown(raw);
    expect(out).toContain('1. 三个"硬骨头"必须有解决方案\n\n');
    expect(out).toContain("| 技术难点 | 外包队伍应对策略 |");
    expect(out).toContain("|---|---|");
    expect(out).not.toMatch(/解决方案 \| 技术难点/);
  });

  it("peels a ## title cell and aligns 3-col header to 2-col body", () => {
    const raw = [
      '| ## 1. 三个"硬骨头"必须有解决方案| 技术难点 | 外包队伍应对策略 |',
      "|---|---|",
      "| 北斗协议栈 (BD 430077.2-2022、BDGGA) | ①团队内培养 1 名专责 |",
      "| 时空 DSL 设计 | 不能直接用 ES DSL 了事 |",
      "| 数据质量引擎 (8 类规则) | 必须自研 |",
    ].join("\n");
    const out = normalizeMarkdown(raw);
    expect(out).toContain('## 1. 三个"硬骨头"必须有解决方案\n\n');
    expect(out).toContain("| 技术难点 | 外包队伍应对策略 |");
    expect(out).toContain("|---|---|");
    expect(out).toContain("| 北斗协议栈");
    expect(out).not.toMatch(/^\| ## /m);
    const headerCols = (out.match(/\| 技术难点 \| 外包队伍应对策略 \|/) || [])[0];
    expect(headerCols).toBeTruthy();
  });
});
