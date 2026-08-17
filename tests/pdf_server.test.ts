import { afterEach, describe, expect, it, vi } from "vitest";

// Mock BrowserWindow before importing pdf_server
const printToPDF = vi.fn().mockResolvedValue(Buffer.from("%PDF-1.4 test"));
const destroy = vi.fn();
const loadURL = vi.fn().mockResolvedValue(undefined);

vi.mock("electron", () => ({
  BrowserWindow: vi.fn().mockImplementation(() => ({
    loadURL,
    webContents: { printToPDF },
    destroy,
  })),
}));

import { startPdfServer } from "../electron/pdf_server";

describe("pdf_server", () => {
  let close: (() => Promise<void>) | null = null;

  afterEach(async () => {
    if (close) {
      await close();
      close = null;
    }
    printToPDF.mockClear();
    loadURL.mockClear();
  });

  it("POST /print-to-pdf returns PDF bytes", async () => {
    const server = await startPdfServer();
    close = server.close;

    const res = await fetch(`http://127.0.0.1:${server.port}/print-to-pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html: "<h1>Hello</h1>" }),
    });

    expect(res.status).toBe(200);
    const buf = Buffer.from(await res.arrayBuffer());
    expect(buf.toString("utf8")).toContain("%PDF-1.4");
    expect(loadURL).toHaveBeenCalled();
    expect(printToPDF).toHaveBeenCalled();
  });
});
