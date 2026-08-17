import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("api", {
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke("backend-url"),
  restartBackend: (): Promise<string> => ipcRenderer.invoke("backend:restart"),
  getKey: (account: string): Promise<string | null> =>
    ipcRenderer.invoke("keychain:get", account),
  setKey: (account: string, value: string): Promise<void> =>
    ipcRenderer.invoke("keychain:set", account, value),
  getModels: (): Promise<unknown> => ipcRenderer.invoke("models:get"),
  upsertModel: (input: unknown): Promise<unknown> =>
    ipcRenderer.invoke("models:upsert", input),
  removeModel: (id: string): Promise<unknown> =>
    ipcRenderer.invoke("models:remove", id),
  setActiveModel: (id: string): Promise<unknown> =>
    ipcRenderer.invoke("models:setActive", id),
  validateModel: (input: unknown): Promise<unknown> =>
    ipcRenderer.invoke("models:validate", input),
  ipcPrintPDF: (_html: string): Promise<Buffer> =>
    ipcRenderer.invoke("print-to-pdf", _html),
  ipcOpenPath: (_path: string): Promise<void> =>
    ipcRenderer.invoke("open-path", _path),
  selectDirectory: (): Promise<string | null> =>
    ipcRenderer.invoke("dialog:select-directory"),
  selectFile: (options?: { title?: string }): Promise<{
    success: boolean;
    canceled?: boolean;
    files?: Array<{ filePath: string; fileName: string }>;
    fileCount?: number;
  }> => ipcRenderer.invoke("dialog:select-files", options),
  readTextFile: (filePath: string): Promise<{ content?: string; error?: string }> =>
    ipcRenderer.invoke("read-text-file", filePath),
  openFile: (
    type: string,
    filePath: string,
    showSource?: boolean,
  ): Promise<string> =>
    ipcRenderer.invoke("open-file", type, filePath, showSource),
  readFileDataUrl: (filePath: string): Promise<string> =>
    ipcRenderer.invoke("read-file-dataurl", filePath),
  readFileBuffer: (
    filePath: string,
  ): Promise<{ ok: boolean; data?: Uint8Array; error?: string }> =>
    ipcRenderer.invoke("read-file-buffer", filePath),
  writeFileBuffer: (
    filePath: string,
    data: Uint8Array,
    options?: { allowCreate?: boolean },
  ): Promise<{ ok: boolean; error?: string }> =>
    ipcRenderer.invoke("write-file-buffer", filePath, data, options),
  saveFileDialog: (options?: {
    defaultPath?: string;
    filters?: Array<{ name: string; extensions: string[] }>;
  }): Promise<{ canceled: boolean; filePath?: string }> =>
    ipcRenderer.invoke("dialog:save-file", options),
  startTunnel: (): Promise<string> => ipcRenderer.invoke("tunnel:start"),
  stopTunnel: (): Promise<void> => ipcRenderer.invoke("tunnel:stop"),
  getTunnelUrl: (): Promise<string | null> => ipcRenderer.invoke("tunnel:url"),
  getCdpBrowsers: (): Promise<unknown[]> => ipcRenderer.invoke("cdp:list"),
  launchCdpBrowser: (): Promise<{ port?: number; error?: string; id?: string }> =>
    ipcRenderer.invoke("cdp:launch"),
  connectCdpBrowser: (port: number): Promise<{ success?: boolean; error?: string }> =>
    ipcRenderer.invoke("cdp:connect", port),
  removeCdpBrowser: (id: string): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke("cdp:remove", id),
  onCdpPoolChanged: (cb: (browsers: unknown[]) => void): (() => void) => {
    const handler = (_: unknown, browsers: unknown[]) => cb(browsers);
    ipcRenderer.on("cdp:pool-changed", handler);
    return () => ipcRenderer.removeListener("cdp:pool-changed", handler);
  },
  checkForUpdates: (): Promise<{ ok: boolean; message: string }> =>
    ipcRenderer.invoke("updater:check"),
});
