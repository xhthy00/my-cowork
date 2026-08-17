/**
 * Deliverable-vs-process file classification (mirror of backend
 * app/workspace/output_files.py). Regression: agent probe files such as
 * t_nf_0.0.xlsx must never surface in the 交付成果 panel.
 */
import { describe, expect, it } from "vitest";

import { isDeliverableOutputPath } from "../../renderer/src/lib/outputFiles";

const PROBES = [
  "t_nf_0.0.xlsx",
  "t_comb1.xlsx",
  "t_h2.xlsx",
  "tC.xlsx",
  "t_nf_#,##0.0.xlsx",
  "t_nf_0.0%.xlsx",
  "t_nf_$#,##0.xlsx",
  "x1_check.xlsx",
  "tmp_build.xlsx",
  "demo.pptx",
];

const REALS = [
  "发货单列表2025_12.xlsx",
  "2025年12月发货单_销售与财务分析.xlsx",
  "table_销售.xlsx",
  "checklist.xlsx",
  "report.docx",
  "趋势图.png",
];

describe("outputFiles probe heuristics", () => {
  it.each(PROBES)("filters probe file %s", (name) => {
    expect(isDeliverableOutputPath(`/tmp/proj/${name}`)).toBe(false);
  });

  it.each(REALS)("keeps real deliverable %s", (name) => {
    expect(isDeliverableOutputPath(`/tmp/proj/${name}`)).toBe(true);
  });

  it("still filters scratch dir and process extensions", () => {
    expect(isDeliverableOutputPath("/tmp/proj/_scratch/report.docx")).toBe(false);
    expect(isDeliverableOutputPath("/tmp/proj/script.py")).toBe(false);
  });
});
