import { describe, expect, it } from "vitest";

import { formatTokenCount, formatTokenUsage } from "../../renderer/src/lib/formatTokens";

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
