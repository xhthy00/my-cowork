/**
 * Adapted from eigent: electron/main/fileReader.ts (preview openFile subset).
 * Converts office/csv files to HTML for the Session Preview panel.
 *
 * Preferred preview path for docx/xlsx/csv: renderer reads via readFileBuffer
 * (docx-preview / SheetJS). openPreviewFile remains a fallback for pptx/doc
 * and legacy open-file callers.
 */
import fs from "node:fs";
import path from "node:path";

import mammoth from "mammoth";
import Papa from "papaparse";
import * as unzipper from "unzipper";
import { parseStringPromise } from "xml2js";

/** Max binary payload for preview IPC (80 MiB). */
export const MAX_PREVIEW_FILE_BYTES = 80 * 1024 * 1024;

/** Decode literal ``\uXXXX`` escapes (JSON/ensure_ascii leftovers) to real chars. */
export function decodeUnicodeEscapes(raw: string): string {
  return String(raw || "").replace(/\\u([0-9a-fA-F]{4})/g, (_, hex: string) =>
    String.fromCharCode(parseInt(hex, 16)),
  );
}

/** First non-empty line — rejects multi-path blobs glued with newlines. */
export function normalizeSinglePath(filePath: string): string {
  const first =
    decodeUnicodeEscapes(String(filePath || ""))
      .split(/[\r\n]+/)
      .map((p) => p.trim())
      .find(Boolean) || "";
  return first;
}

/** Resolve + validate absolute file path for preview buffer I/O. */
export function resolvePreviewPath(filePath: string): string {
  const raw = normalizeSinglePath(filePath);
  if (!raw) throw new Error("empty path");
  const resolved = path.resolve(raw);
  if (!path.isAbsolute(resolved)) throw new Error("path must be absolute");
  return resolved;
}

export function readPreviewFileBuffer(filePath: string): Uint8Array {
  const resolved = resolvePreviewPath(filePath);
  if (!fs.existsSync(resolved)) throw new Error(`File not found: ${resolved}`);
  const st = fs.statSync(resolved);
  if (!st.isFile()) throw new Error(`Not a file: ${resolved}`);
  if (st.size > MAX_PREVIEW_FILE_BYTES) {
    throw new Error(
      `File too large for in-app preview (${Math.ceil(st.size / (1024 * 1024))}MB > 80MB)`,
    );
  }
  return new Uint8Array(fs.readFileSync(resolved));
}

export function writePreviewFileBuffer(
  filePath: string,
  data: Uint8Array,
  opts?: { allowCreate?: boolean },
): void {
  const resolved = resolvePreviewPath(filePath);
  const allowCreate = opts?.allowCreate === true;
  if (fs.existsSync(resolved)) {
    const st = fs.statSync(resolved);
    if (!st.isFile()) throw new Error(`Not a file: ${resolved}`);
  } else if (!allowCreate) {
    throw new Error(`File does not exist (use save-as to create): ${resolved}`);
  } else {
    const parent = path.dirname(resolved);
    if (!fs.existsSync(parent) || !fs.statSync(parent).isDirectory()) {
      throw new Error(`Parent directory missing: ${parent}`);
    }
  }
  if (data.byteLength > MAX_PREVIEW_FILE_BYTES) {
    throw new Error("Payload too large (>80MB)");
  }
  fs.writeFileSync(resolved, Buffer.from(data));
}

function columnToNumber(column: string): number {
  let result = 0;
  for (let i = 0; i < column.length; i++) {
    result = result * 26 + (column.charCodeAt(i) - "A".charCodeAt(0) + 1);
  }
  return result;
}

function numberToColumn(num: number): string {
  let column = "";
  let n = num;
  while (n > 0) {
    n--;
    column = String.fromCharCode((n % 26) + "A".charCodeAt(0)) + column;
    n = Math.floor(n / 26);
  }
  return column;
}

function getCellValue(cell: any, sharedStrings: string[]): string {
  try {
    if (cell.v && cell.v[0] !== undefined) {
      const value = cell.v[0];
      if (cell.$ && cell.$.t === "s") {
        const index = parseInt(value, 10);
        if (!isNaN(index) && index >= 0 && index < sharedStrings.length) {
          return sharedStrings[index] || "";
        }
        return String(value);
      }
      if (cell.$ && cell.$.t === "inlineStr") {
        return cell.is?.[0]?.t?.[0] || "";
      }
      if (cell.$ && cell.$.t === "str") {
        return value;
      }
      const numValue = parseFloat(value);
      if (!isNaN(numValue) && numValue % 1 !== 0) {
        return numValue.toFixed(2);
      }
      return value;
    }
    if (cell.is?.[0]?.t?.[0]) return cell.is[0].t[0];
    if (cell.f?.[0] && cell.v?.[0]) return cell.v[0];
    return "";
  } catch {
    return "";
  }
}

async function parseDocx(filePath: string): Promise<string> {
  const result = await mammoth.convertToHtml({ path: filePath });
  return result.value;
}

async function parsePptx(filePath: string): Promise<string> {
  const directory = await unzipper.Open.file(filePath);
  const slideFiles = directory.files.filter((f) =>
    /^ppt\/slides\/slide\d+\.xml$/.test(f.path),
  );
  let html = '<div style="font-family: sans-serif;">';
  for (let i = 0; i < slideFiles.length; i++) {
    const contentBuffer = await slideFiles[i].buffer();
    const parsed = await parseStringPromise(contentBuffer.toString("utf-8"));
    html += `<h3>Slide ${i + 1}</h3><ul>`;
    const texts = parsed["p:sld"]?.["p:cSld"]?.[0]?.["p:spTree"]?.[0]?.["p:sp"] || [];
    for (const textNode of texts) {
      const paras = textNode?.["p:txBody"]?.[0]?.["a:p"] || [];
      for (const para of paras) {
        for (const run of para?.["a:r"] || []) {
          const text = run?.["a:t"]?.[0];
          if (text) html += `<li>${text}</li>`;
        }
      }
    }
    html += "</ul><hr/>";
  }
  html += "</div>";
  return html;
}

async function parseXlsx(filePath: string): Promise<string> {
  const directory = await unzipper.Open.file(filePath);
  const sharedStringsFile = directory.files.find(
    (f) => f.path === "xl/sharedStrings.xml",
  );
  const worksheetFiles = directory.files.filter((f) =>
    /^xl\/worksheets\/sheet\d+\.xml$/.test(f.path),
  );

  let sharedStrings: string[] = [];
  if (sharedStringsFile) {
    const sharedStringsContent = (
      await sharedStringsFile.buffer()
    ).toString("utf-8");
    const parsedSharedStrings = await parseStringPromise(sharedStringsContent);
    if (parsedSharedStrings.sst?.si) {
      sharedStrings = parsedSharedStrings.sst.si.map((si: any) => {
        if (si.t?.[0]) {
          return typeof si.t[0] === "string" ? si.t[0] : String(si.t[0]);
        }
        if (si.r) {
          return si.r
            .map((r: any) =>
              r.t?.[0]
                ? typeof r.t[0] === "string"
                  ? r.t[0]
                  : String(r.t[0])
                : "",
            )
            .join("");
        }
        return typeof si === "string" ? si : "";
      });
    }
  }

  let html = `
    <style>
      .xlsx-container { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 20px; }
      .xlsx-table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 14px; }
      .xlsx-table th { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 12px 8px; text-align: left; font-weight: 600; }
      .xlsx-table td { border: 1px solid #dee2e6; padding: 8px; }
      .xlsx-table tr:nth-child(even) { background-color: #f8f9fa; }
      .sheet-title { font-size: 18px; font-weight: 600; margin: 20px 0 10px 0; }
    </style>
    <div class="xlsx-container">
  `;

  for (let i = 0; i < worksheetFiles.length && i < 5; i++) {
    const content = (await worksheetFiles[i].buffer()).toString("utf-8");
    const parsed = await parseStringPromise(content);
    if (worksheetFiles.length > 1) {
      html += `<h3 class="sheet-title">Sheet ${i + 1}</h3>`;
    }
    html += '<table class="xlsx-table">';
    const rows = parsed.worksheet?.sheetData?.[0]?.row || [];
    let maxCol = 0;
    for (const row of rows) {
      for (const cell of row.c || []) {
        if (cell.$?.r) {
          const colMatch = String(cell.$.r).match(/^([A-Z]+)/);
          if (colMatch) maxCol = Math.max(maxCol, columnToNumber(colMatch[1]));
        }
      }
    }
    html += '<thead><tr><th style="background-color:#e9ecef;width:50px;"></th>';
    for (let c = 0; c < maxCol; c++) {
      html += `<th>${numberToColumn(c + 1)}</th>`;
    }
    html += "</tr></thead><tbody>";
    for (const row of rows) {
      const rowNum = row.$?.r ?? "";
      html += `<tr><th style="background-color:#e9ecef;text-align:center;">${rowNum}</th>`;
      const cellMap = new Map<number, any>();
      for (const cell of row.c || []) {
        if (cell.$?.r) {
          const colMatch = String(cell.$.r).match(/^([A-Z]+)/);
          if (colMatch) cellMap.set(columnToNumber(colMatch[1]), cell);
        }
      }
      for (let c = 1; c <= maxCol; c++) {
        const cell = cellMap.get(c);
        html += `<td>${cell ? getCellValue(cell, sharedStrings) : ""}</td>`;
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
  }
  html += "</div>";
  return html;
}

async function parseCsv(filePath: string): Promise<string> {
  const fileContent = fs.readFileSync(filePath, "utf-8");
  const result = Papa.parse(fileContent, {
    header: true,
    skipEmptyLines: true,
    delimiter: ",",
  });
  if (!result.data?.length) return "<p>Empty CSV file</p>";
  const headers = Object.keys(result.data[0] as Record<string, unknown>);
  let html =
    '<table style="border-collapse:collapse;width:100%;font-family:monospace;">';
  html += '<thead><tr style="background-color:#f5f5f5;">';
  for (const header of headers) {
    html += `<th style="border:1px solid #ddd;padding:8px;text-align:left;">${header}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const row of result.data as Record<string, string>[]) {
    html += "<tr>";
    for (const header of headers) {
      html += `<td style="border:1px solid #ddd;padding:8px;">${row[header] || ""}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return html;
}

/** Eigent-aligned: return HTML / text / path for Session Preview. */
export async function openPreviewFile(
  type: string,
  filePath: string,
): Promise<string> {
  const resolved = path.resolve(normalizeSinglePath(filePath));
  if (!fs.existsSync(resolved)) {
    throw new Error(`File not found: ${resolved}`);
  }
  const t = (type || path.extname(resolved).slice(1)).toLowerCase();

  if (t === "md" || t === "html" || t === "htm") {
    return fs.readFileSync(resolved, "utf-8");
  }
  if (t === "pdf") {
    return resolved;
  }
  if (t === "csv") {
    try {
      return await parseCsv(resolved);
    } catch {
      return fs.readFileSync(resolved, "utf-8");
    }
  }
  if (t === "docx" || t === "doc") {
    try {
      return await parseDocx(resolved);
    } catch {
      return fs.readFileSync(resolved, "utf-8");
    }
  }
  if (t === "pptx") {
    try {
      return await parsePptx(resolved);
    } catch {
      return `<pre>${fs.readFileSync(resolved).toString("base64")}</pre>`;
    }
  }
  if (t === "xlsx") {
    try {
      return await parseXlsx(resolved);
    } catch {
      return fs.readFileSync(resolved, "utf-8");
    }
  }
  return fs.readFileSync(resolved, "utf-8");
}

export function fileToDataUrl(filePath: string): string {
  const resolved = path.resolve(normalizeSinglePath(filePath));
  const buf = fs.readFileSync(resolved);
  const ext = path.extname(resolved).toLowerCase();
  const mimeMap: Record<string, string> = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
  };
  const mimeType = mimeMap[ext] || "application/octet-stream";
  return `data:${mimeType};base64,${buf.toString("base64")}`;
}
