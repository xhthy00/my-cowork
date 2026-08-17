import { describe, expect, it } from "vitest";

import { extOf } from "../../renderer/src/components/preview/FilePreview";

describe("FilePreview extOf", () => {
  it("extracts lowercase extension from path", () => {
    expect(extOf("/Users/me/a/关于议案.docx")).toBe("docx");
    expect(extOf("report.PPTX")).toBe("pptx");
    expect(extOf("sheet.xlsx")).toBe("xlsx");
    expect(extOf("doc.pdf")).toBe("pdf");
    expect(extOf("readme.md")).toBe("md");
  });
});
