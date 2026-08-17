/**
 * SheetJS helpers for spreadsheet preview + lightweight cell-value editing.
 * Locked to xlsx@0.18.5 (SheetJS Community Edition).
 */
import * as XLSX from "xlsx";

/** Soft cap: above this, editor becomes read-only truncated preview. */
export const MAX_EDITABLE_CELLS = 30_000;

/** Rows shown in large-file read-only mode. */
export const LARGE_FILE_PREVIEW_ROWS = 500;

export type SheetModel = {
  name: string;
  grid: string[][];
};

export type WorkbookModel = {
  sheets: SheetModel[];
  active: number;
  cellCount: number;
  readOnly: boolean;
};

function toCellString(v: unknown): string {
  if (v == null) return "";
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  return String(v);
}

/** Pad jagged AOA into a rectangle. */
export function normalizeGrid(rows: unknown[][]): string[][] {
  const maxCols = rows.reduce((m, r) => Math.max(m, Array.isArray(r) ? r.length : 0), 0);
  if (maxCols === 0) return [[""]];
  return rows.map((r) => {
    const row = Array.isArray(r) ? r : [];
    const out: string[] = [];
    for (let c = 0; c < maxCols; c++) out.push(toCellString(row[c]));
    return out;
  });
}

export function countCells(sheets: SheetModel[]): number {
  return sheets.reduce(
    (n, s) => n + s.grid.reduce((m, row) => m + row.length, 0),
    0,
  );
}

export function gridsEqual(a: string[][], b: string[][]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i].length !== b[i].length) return false;
    for (let j = 0; j < a[i].length; j++) {
      if (a[i][j] !== b[i][j]) return false;
    }
  }
  return true;
}

export function columnLabel(index0: number): string {
  let n = index0 + 1;
  let col = "";
  while (n > 0) {
    n--;
    col = String.fromCharCode((n % 26) + 65) + col;
    n = Math.floor(n / 26);
  }
  return col;
}

export function parseWorkbookBuffer(
  data: Uint8Array,
  ext: "xlsx" | "csv",
): WorkbookModel {
  const wb = XLSX.read(data, {
    type: "array",
    cellDates: true,
    raw: false,
  });
  const sheets: SheetModel[] = [];
  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    const aoa = XLSX.utils.sheet_to_json(ws, {
      header: 1,
      defval: "",
      raw: false,
    }) as unknown[][];
    sheets.push({ name, grid: normalizeGrid(aoa) });
  }
  if (!sheets.length) {
    sheets.push({ name: ext === "csv" ? "Sheet1" : "Sheet1", grid: [[""]] });
  }
  const cellCount = countCells(sheets);
  return {
    sheets,
    active: 0,
    cellCount,
    readOnly: cellCount > MAX_EDITABLE_CELLS,
  };
}

/** Build xlsx bytes from edited sheets (values only; formulas become constants). */
export function serializeXlsx(sheets: SheetModel[]): Uint8Array {
  const wb = XLSX.utils.book_new();
  for (const sheet of sheets) {
    const ws = XLSX.utils.aoa_to_sheet(sheet.grid);
    XLSX.utils.book_append_sheet(wb, ws, sheet.name.slice(0, 31) || "Sheet");
  }
  const out = XLSX.write(wb, { bookType: "xlsx", type: "array" }) as ArrayBuffer;
  return new Uint8Array(out);
}

/** UTF-8 CSV (no BOM) from first sheet. */
export function serializeCsv(sheet: SheetModel): Uint8Array {
  const ws = XLSX.utils.aoa_to_sheet(sheet.grid);
  const csv = XLSX.utils.sheet_to_csv(ws);
  return new TextEncoder().encode(csv);
}

/** Truncate grids for large read-only display. */
export function truncateForPreview(sheets: SheetModel[]): SheetModel[] {
  return sheets.map((s) => ({
    name: s.name,
    grid: s.grid.slice(0, LARGE_FILE_PREVIEW_ROWS),
  }));
}

export function setCell(
  grid: string[][],
  row: number,
  col: number,
  value: string,
): string[][] {
  const next = grid.map((r) => r.slice());
  while (next.length <= row) next.push([]);
  const maxCols = Math.max(
    col + 1,
    ...next.map((r) => r.length),
    grid[0]?.length ?? 0,
  );
  for (let i = 0; i < next.length; i++) {
    while (next[i].length < maxCols) next[i].push("");
  }
  next[row][col] = value;
  return next;
}
