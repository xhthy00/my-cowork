import { describe, expect, it } from "vitest";

import {
  DEFAULT_CONTEXT_LIMIT,
  formatContextUsedLabel,
  formatContextUsedStats,
  formatTokenCount,
  formatTokenK,
  formatTokenUsage,
  resolveContextUsage,
} from "../../renderer/src/lib/formatTokens";

describe("formatTokenCount", () => {
  it("formats small counts with locale separators", () => {
    expect(formatTokenCount(0)).toBe("0");
    expect(formatTokenCount(1234)).toBe("1,234");
  });

  it("formats large counts in 万", () => {
    expect(formatTokenCount(100_000)).toBe("10万");
    expect(formatTokenCount(123_456)).toBe("12.3万");
  });

  it("formatTokenUsage includes max when provided", () => {
    expect(formatTokenUsage(1200, 200_000)).toBe("1,200 / 20万 tokens");
    expect(formatTokenUsage(50)).toBe("50 tokens");
  });
});

describe("formatTokenK", () => {
  it("uses WorkBuddy-style K with one decimal", () => {
    expect(formatTokenK(98200)).toBe("98.2K");
    expect(formatTokenK(192000)).toBe("192.0K");
    expect(formatTokenK(400)).toBe("400");
    expect(formatTokenK(1_000_000)).toBe('1.0M');
  });
});

describe("formatContextUsedLabel", () => {
  it("matches WorkBuddy occupancy copy", () => {
    expect(formatContextUsedStats(98200, 192000)).toBe("51.1% · 98.2K / 192.0K");
    expect(formatContextUsedLabel(98200, 192000)).toBe(
      "51.1% · 98.2K / 192.0K 上下文已使用",
    );
  });
});

describe("resolveContextUsage", () => {
  it("keeps model context capacity independent of a task token cap", () => {
    const usage = resolveContextUsage({ contextTokens: 50_000, budgetMaxTokens: 10_000 });
    expect(usage.limit).toBe(DEFAULT_CONTEXT_LIMIT);
    expect(usage.percentage).toBe(0);
    expect(formatContextUsedLabel(usage.used, usage.limit)).toBe('约 50.0K tokens · 上下文窗口未知');
  });

  it("shows zero occupancy for an empty conversation", () => {
    const empty = resolveContextUsage({ messages: [] });
    expect(empty.limit).toBe(DEFAULT_CONTEXT_LIMIT);
    expect(empty.used).toBe(0);
    expect(empty.percentage).toBe(0);
  });

  it("prefers last prompt occupancy from the backend", () => {
    const live = resolveContextUsage({
      messages: [{ content: "hi" }],
      contextTokens: 98200,
      contextLimit: 192000,
    });
    expect(live.used).toBe(98200);
    expect(live.limit).toBe(192000);
    expect(live.percentage).toBeCloseTo(51.1458, 3);
  });

  it('allows occupancy to decrease after compaction despite a long saved transcript', () => {
    const usage = resolveContextUsage({ messages: [{content: '历史'.repeat(30_000)}],
      contextTokens: 2_000, contextLimit: 1_000_000 });
    expect(usage.used).toBe(2_000);
    expect(usage.percentage).toBeCloseTo(0.2);
  });
});
