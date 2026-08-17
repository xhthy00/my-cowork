import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";

import {
  columnLabel,
  countCells,
  gridsEqual,
  MAX_EDITABLE_CELLS,
  normalizeGrid,
  parseWorkbookBuffer,
  serializeCsv,
  serializeXlsx,
  setCell,
} from "../../renderer/src/lib/sheetjs";

describe("sheetjs helpers", () => {
  it("columnLabel maps 0-based index to Excel letters", () => {
    expect(columnLabel(0)).toBe("A");
    expect(columnLabel(25)).toBe("Z");
    expect(columnLabel(26)).toBe("AA");
  });

  it("normalizeGrid pads jagged rows", () => {
    const g = normalizeGrid([["a"], ["b", "c", "d"]]);
    expect(g).toEqual([
      ["a", "", ""],
      ["b", "c", "d"],
    ]);
  });

  it("gridsEqual and setCell track edits", () => {
    const a = [
      ["1", "2"],
      ["3", "4"],
    ];
    const b = setCell(a, 0, 1, "9");
    expect(gridsEqual(a, b)).toBe(false);
    expect(b[0][1]).toBe("9");
    expect(a[0][1]).toBe("2");
  });

  it("xlsx roundtrip preserves cell values", () => {
    const sheets = [
      {
        name: "Data",
        grid: [
          ["Name", "Qty"],
          ["Apple", "3"],
          ["Tea", "2"],
        ],
      },
      {
        name: "Notes",
        grid: [["hello"]],
      },
    ];
    const buf = serializeXlsx(sheets);
    const model = parseWorkbookBuffer(buf, "xlsx");
    expect(model.sheets).toHaveLength(2);
    expect(model.sheets[0].name).toBe("Data");
    expect(model.sheets[0].grid[1][0]).toBe("Apple");
    expect(model.sheets[1].grid[0][0]).toBe("hello");
    expect(model.readOnly).toBe(false);
  });

  it("csv roundtrip via serializeCsv + SheetJS read", () => {
    const sheet = {
      name: "Sheet1",
      grid: [
        ["a", "b"],
        ["1", "2"],
      ],
    };
    const bytes = serializeCsv(sheet);
    const model = parseWorkbookBuffer(bytes, "csv");
    expect(model.sheets[0].grid[0]).toEqual(["a", "b"]);
    expect(model.sheets[0].grid[1]).toEqual(["1", "2"]);
  });

  it("marks oversized workbooks read-only", () => {
    const wb = XLSX.utils.book_new();
    const rows: string[][] = [];
    const cols = 100;
    const neededRows = Math.ceil((MAX_EDITABLE_CELLS + 1) / cols);
    for (let r = 0; r < neededRows; r++) {
      rows.push(Array.from({ length: cols }, (_, c) => `${r},${c}`));
    }
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(rows), "Big");
    const buf = new Uint8Array(
      XLSX.write(wb, { bookType: "xlsx", type: "array" }) as ArrayBuffer,
    );
    const model = parseWorkbookBuffer(buf, "xlsx");
    expect(model.cellCount).toBeGreaterThan(MAX_EDITABLE_CELLS);
    expect(model.readOnly).toBe(true);
    expect(countCells(model.sheets)).toBe(model.cellCount);
  });
});
