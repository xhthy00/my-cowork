import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  MAX_PREVIEW_FILE_BYTES,
  readPreviewFileBuffer,
  writePreviewFileBuffer,
} from "../electron/fileReader";

const tmpFiles: string[] = [];

afterEach(() => {
  for (const f of tmpFiles.splice(0)) {
    try {
      fs.unlinkSync(f);
    } catch {
      /* ignore */
    }
  }
});

describe("preview file buffer I/O", () => {
  it("reads and writes binary roundtrip", () => {
    const p = path.join(os.tmpdir(), `mycowork-preview-${Date.now()}.bin`);
    tmpFiles.push(p);
    fs.writeFileSync(p, Buffer.from([1, 2, 3, 4]));
    const data = readPreviewFileBuffer(p);
    expect(Array.from(data)).toEqual([1, 2, 3, 4]);
    writePreviewFileBuffer(p, new Uint8Array([9, 8]));
    expect(Array.from(fs.readFileSync(p))).toEqual([9, 8]);
  });

  it("rejects overwrite of missing file without allowCreate", () => {
    const p = path.join(os.tmpdir(), `mycowork-missing-${Date.now()}.bin`);
    expect(() => writePreviewFileBuffer(p, new Uint8Array([1]))).toThrow(
      /does not exist/,
    );
  });

  it("creates file when allowCreate", () => {
    const p = path.join(os.tmpdir(), `mycowork-create-${Date.now()}.bin`);
    tmpFiles.push(p);
    writePreviewFileBuffer(p, new Uint8Array([7]), { allowCreate: true });
    expect(fs.readFileSync(p)[0]).toBe(7);
  });

  it("exports size constant", () => {
    expect(MAX_PREVIEW_FILE_BYTES).toBe(80 * 1024 * 1024);
  });
});
