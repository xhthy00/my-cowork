import { describe, expect, it } from "vitest";

import { extractFinalOutputFileList } from "../../renderer/src/lib/extractFinalOutputFiles";

describe("extractFinalOutputFileList (Eigent)", () => {
  it("keeps supported absolute POSIX and Windows paths", () => {
    const files = extractFinalOutputFileList(
      "Outputs: /Users/test/report.md and C:\\Users\\test\\report.xlsx",
    );
    expect(files.map((file) => file.path)).toEqual([
      "/Users/test/report.md",
      "C:/Users/test/report.xlsx",
    ]);
  });

  it("extracts html deliverable from a Chinese summary", () => {
    const files = extractFinalOutputFileList(
      "数据分析 HTML报告已生成。\n文件路径: /Users/tanghaoyu/Documents/AIS/高三4次模拟数据分析报告.html",
    );
    expect(files).toHaveLength(1);
    expect(files[0]?.path).toBe(
      "/Users/tanghaoyu/Documents/AIS/高三4次模拟数据分析报告.html",
    );
    expect(files[0]?.kind).toBe("file");
  });

  it("does not turn https URLs into files", () => {
    expect(
      extractFinalOutputFileList("see https://example.com/report.html"),
    ).toEqual([]);
  });
});
