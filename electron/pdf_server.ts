/**
 * Local HTTP bridge so Python can request printToPDF without weasyprint.
 * Listens on 127.0.0.1:0 and exposes POST /print-to-pdf { html: string }.
 */
import { BrowserWindow } from "electron";
import * as http from "http";

export interface PdfServer {
  port: number;
  close: () => Promise<void>;
}

export function startPdfServer(): Promise<PdfServer> {
  const server = http.createServer(async (req, res) => {
    if (req.method === "POST" && req.url === "/print-to-pdf") {
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      }
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8")) as { html?: string };
        const html = body.html ?? "";
        const pdf = await renderHtmlToPdf(html);
        res.writeHead(200, { "Content-Type": "application/pdf" });
        res.end(pdf);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.writeHead(500, { "Content-Type": "text/plain" });
        res.end(message);
      }
      return;
    }
    res.writeHead(404);
    res.end("not found");
  });

  return new Promise((resolve, reject) => {
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (!addr || typeof addr === "string") {
        reject(new Error("failed to bind PDF server"));
        return;
      }
      resolve({
        port: addr.port,
        close: () =>
          new Promise((res, rej) => {
            server.close((err) => (err ? rej(err) : res()));
          }),
      });
    });
    server.on("error", reject);
  });
}

async function renderHtmlToPdf(html: string): Promise<Buffer> {
  const win = new BrowserWindow({
    show: false,
    width: 800,
    height: 600,
    webPreferences: { offscreen: true },
  });
  try {
    const dataUrl = `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
    await win.loadURL(dataUrl);
    const pdf = await win.webContents.printToPDF({ printBackground: true });
    return Buffer.from(pdf);
  } finally {
    win.destroy();
  }
}
