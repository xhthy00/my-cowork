/**
 * @vitest-environment jsdom
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MessageContent, {
  beautifyChatMarkdown,
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

  it("drops leaked search-narration after </think> instead of showing it as the answer", () => {
    const raw = [
      "<think>",
      "- 扬州已取消限购",
      "</think>",
      "我将开始调研扬州",
      "继续查询公积金、人才补贴",
      "让我深入获取最新政策。",
    ].join("\n");
    const segs = parseContentSegments(raw);
    expect(segs.some((s) => s.type === "answer")).toBe(false);
    const think = segs
      .filter((s) => s.type === "think")
      .map((s) => s.text)
      .join("\n");
    expect(think).toContain("取消限购");
    expect(think).not.toContain("我将开始调研扬州");
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

  it("collapses a closed think to 工作过程", () => {
    const content = ["<think>", "done thinking", "</think>", "最终答案"].join("\n");
    render(<MessageContent content={content} role="assistant" />);
    const details = document.querySelectorAll("details.deep-think");
    expect(details).toHaveLength(1);
    expect(details[0]?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("工作过程")).toBeInTheDocument();
    expect(screen.getByText(/最终答案/)).toBeInTheDocument();
  });

  it("merges multiple thinks into one process summary", () => {
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
    expect(screen.getByText("工作过程")).toBeInTheDocument();
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
    expect(screen.queryByText("工作过程")).not.toBeInTheDocument();
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

  it("detaches code fences glued to a heading and the last line", () => {
    const raw = [
      "四、APP申请流程示意图```",
      "└── 我的 — 实名认证 (身份证+人脸)",
      "推送给开发企业 — 首付款直接抵扣```",
      "五、常见卡点与解决方法",
    ].join("\n");
    const out = normalizeMarkdown(raw);
    expect(out).toContain("四、APP申请流程示意图\n```\n");
    expect(out).toContain("首付款直接抵扣\n```\n五、");
    expect(out).not.toContain("示意图```");
    expect(out).not.toContain("抵扣```");
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

  it("repairs a MiniMax 操作说明 table glued to a | - list item", () => {
    const raw = [
      "- UI 显示: 生命值、分数、剩余敌人、当前关卡",
      "| - 通关系统: 消灭全部20 辆敌人后弹出胜利界面",
      "🕹️ 操作说明 | 按键 | 功能 |",
      "|---|---|---|",
      "| ↑ ↓ ← → 或 W/A/S/D | 移动坦克 ||",
      "| 空格键 (按住) | 连续发射子弹 ||",
      "| Enter | 游戏结束后重新开始 ||",
      "",
      "**技术实现**",
    ].join("\n");
    const out = normalizeMarkdown(raw);
    expect(out).toMatch(/^- 通关系统:/m);
    expect(out).not.toMatch(/^\|\s+- 通关系统/m);
    expect(out).toContain("| 🕹️ 操作说明 | 按键 | 功能 |");
    expect(out).toMatch(/\n\n\| 🕹️ 操作说明/);
    expect(out).toContain("| ↑ ↓ ← → 或 W/A/S/D | 移动坦克 |");
    expect(out).not.toMatch(/移动坦克 \|\|/);
  });

  it("renders the glued 操作说明 block as a real HTML table", () => {
    const raw = [
      "| - 通关系统: 消灭全部20 辆敌人后弹出胜利界面",
      "🕹️ 操作说明 | 按键 | 功能 |",
      "|---|---|---|",
      "| ↑ ↓ ← → 或 W/A/S/D | 移动坦克 ||",
      "| 空格键 (按住) | 连续发射子弹 ||",
      "| Enter | 游戏结束后重新开始 ||",
    ].join("\n");
    const { container } = render(
      <MessageContent content={raw} role="assistant" hideThink verbatim />,
    );
    const table = container.querySelector("table");
    expect(table).toBeTruthy();
    expect(table?.textContent).toMatch(/移动坦克/);
    expect(table?.textContent).toMatch(/空格键/);
    expect(container.textContent).not.toContain("|---|");
    expect(container.textContent).toMatch(/通关系统/);
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

describe("beautifyChatMarkdown", () => {
  it("promotes a short title line and quotes 来源 lines", () => {
    const raw = [
      "核心政策结论（含出处）",
      "",
      "1. **限购限售：均已全面取消**",
      "2024年5月起扬州全市取消限购。",
      "来源：新浪财经 https://example.com/a",
    ].join("\n");
    const out = beautifyChatMarkdown(raw);
    expect(out.startsWith("## 核心政策结论（含出处）")).toBe(true);
    expect(out).toContain("> **来源** · 新浪财经 https://example.com/a");
  });

  it("does not promote a full sentence as a title", () => {
    expect(beautifyChatMarkdown("扬州已取消限购。")).toBe("扬州已取消限购。");
  });

  it("pulls indented 2. 3. 4. back to one ordered list", () => {
    const raw = [
      "## 核心政策结论（含出处）",
      "",
      "1. **限购限售：均已全面取消**",
      "2024年5月起扬州全市取消限购。",
      "来源：新浪财经",
      "   2. **房贷利率（2024 年 LPR 调整后）**",
      "      首套房 3.05%。",
      "      3. **契税新政（2024.11.13 起）**",
      "         4. **公积金阶段性提额**",
    ].join("\n");
    const out = beautifyChatMarkdown(raw);
    expect(out).toMatch(/^### 1\. 限购限售/m);
    expect(out).toMatch(/^### 2\. 房贷利率/m);
    expect(out).toMatch(/^### 3\. 契税新政/m);
    expect(out).toMatch(/^### 4\. 公积金阶段性提额/m);
    expect(out).not.toMatch(/^[ \t]+2\./m);
    expect(out).not.toMatch(/^[ \t]+3\./m);
    expect(out).not.toMatch(/^[ \t]+4\./m);
  });

  it("promotes bold numbered titles to headings instead of list cards", () => {
    const out = beautifyChatMarkdown(
      [
        "## 六、投资建议",
        "",
        "1. **已中签者——分批兑现**",
        "长鑫科技建议分批兑现。",
        "2. **未中签、想二级买入者——观望为主**",
      ].join("\n"),
    );
    expect(out).toContain("### 1. 已中签者——分批兑现");
    expect(out).toContain("### 2. 未中签、想二级买入者——观望为主");
    expect(out).toContain("长鑫科技建议分批兑现。");
  });

  it("keeps a nested list that restarts at 1", () => {
    const raw = [
      "1. 主点",
      "   1. 子点 A",
      "   2. 子点 B",
      "2. 下一项",
    ].join("\n");
    const out = beautifyChatMarkdown(raw);
    expect(out).toContain("   1. 子点 A");
    expect(out).toMatch(/^2\. 下一项$/m);
  });
});

describe("streaming / callout markdown", () => {
  it("strips leaked closing tags and half-typed tags while streaming", () => {
    expect(normalizeMarkdown("</div>\n正文")).toBe("正文");
    expect(normalizeMarkdown("hello <div")).toBe("hello ");
  });

  it("marks warning callouts on 注意 blockquotes", () => {
    const { container } = render(
      <MessageContent content={"> 注意：限购已取消"} role="assistant" hideThink verbatim />,
    );
    expect(container.querySelector("blockquote.md-callout-warning")).toBeTruthy();
  });
});
