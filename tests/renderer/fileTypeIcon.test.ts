/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import {
  extOfPath,
  fileTypeKind,
  fileTypeMeta,
} from "../../renderer/src/components/files/FileTypeIcon";

describe("fileTypeKind", () => {
  it("maps office and media extensions", () => {
    expect(fileTypeKind("a.docx")).toBe("docx");
    expect(fileTypeKind("b.xlsx")).toBe("xlsx");
    expect(fileTypeKind("c.pptx")).toBe("pptx");
    expect(fileTypeKind("d.pdf")).toBe("pdf");
    expect(fileTypeKind("e.md")).toBe("md");
    expect(fileTypeKind("shot.png")).toBe("image");
    expect(fileTypeKind("script.py")).toBe("code");
  });

  it("respects artifact kind hint", () => {
    expect(fileTypeKind("unknown", "pptx")).toBe("pptx");
  });

  it("returns meta colors and labels", () => {
    expect(fileTypeMeta("report.docx").label).toBe("Word");
    expect(fileTypeMeta("sheet.xlsx").badge).toContain("00a63e");
    expect(extOfPath("/tmp/a.PDF")).toBe("pdf");
  });
});
