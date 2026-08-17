/**
 * @vitest-environment jsdom
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MessageContent, {
  collectThinkSegments,
  hasVisibleAnswer,
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

  it("keeps each think next to its following answer instead of merging", () => {
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
    const kids = Array.from(container.firstElementChild?.children ?? []);
    expect(kids).toHaveLength(4);
    expect(kids[0]?.classList.contains("deep-think")).toBe(true);
    expect(kids[1]?.textContent).toMatch(/回答一/);
    expect(kids[2]?.classList.contains("deep-think")).toBe(true);
    expect(kids[3]?.textContent).toMatch(/回答二/);
    expect(kids[0]?.textContent).toMatch(/step1/);
    expect(kids[0]?.textContent).not.toMatch(/step2/);
    expect(kids[2]?.textContent).toMatch(/step2/);
    expect(screen.getAllByText("深度思考")).toHaveLength(2);
    expect(screen.queryByText("已思考 · 2 步")).not.toBeInTheDocument();
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

describe("normalizeMarkdownTables", () => {
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
});
