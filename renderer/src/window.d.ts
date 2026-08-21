export type ModelProvider =
  | "anthropic"
  | "openai_compat"
  | "openrouter"
  | "ollama"
  | "lmstudio"
  | "vllm";

export type ModelCategory = "cloud_byok" | "local";

export interface ModelProfile {
  id: string;
  name: string;
  provider: ModelProvider;
  model: string;
  baseUrl?: string;
  isValid?: boolean;
  lastValidatedAt?: string;
  category?: ModelCategory;
  presetId?: string;
}

export interface ModelsState {
  profiles: ModelProfile[];
  activeId: string | null;
}

export interface ModelValidateResult {
  ok: boolean;
  error?: string;
  latency_ms?: number;
}

export interface CdpBrowserInfo {
  id: string;
  port: number;
  name?: string;
  isExternal?: boolean;
  addedAt?: number;
}

export interface ElectronAPI {
  getBackendUrl(): Promise<string>;
  restartBackend(): Promise<string>;
  getKey(account: string): Promise<string | null>;
  setKey(account: string, value: string): Promise<void>;
  getModels(): Promise<ModelsState>;
  upsertModel(input: {
    id?: string;
    name: string;
    provider: ModelProvider;
    model: string;
    baseUrl?: string;
    apiKey?: string;
    activate?: boolean;
    isValid?: boolean;
    lastValidatedAt?: string;
    category?: ModelCategory;
    presetId?: string;
  }): Promise<ModelsState>;
  removeModel(id: string): Promise<ModelsState>;
  setActiveModel(id: string): Promise<ModelsState>;
  validateModel?(input: {
    provider: ModelProvider;
    model: string;
    apiKey?: string;
    baseUrl?: string;
  }): Promise<ModelValidateResult>;
  ipcPrintPDF(html: string): Promise<Buffer>;
  ipcOpenPath(path: string): Promise<void>;
  selectDirectory?(): Promise<string | null>;
  selectFile?(options?: { title?: string }): Promise<{
    success: boolean;
    canceled?: boolean;
    files?: Array<{ filePath: string; fileName: string }>;
    fileCount?: number;
  }>;
  readTextFile?(path: string): Promise<{ content?: string; error?: string }>;
  /** Eigent open-file: returns HTML/text (or path for pdf). */
  openFile?(type: string, path: string, showSource?: boolean): Promise<string>;
  /** Eigent read-file-dataurl for PDF/images. */
  readFileDataUrl?(path: string): Promise<string>;
  /** Binary read for docx-preview / SheetJS. */
  readFileBuffer?(
    path: string,
  ): Promise<{ ok: boolean; data?: Uint8Array; error?: string }>;
  /** Binary write for spreadsheet save / save-as. */
  writeFileBuffer?(
    path: string,
    data: Uint8Array,
    options?: { allowCreate?: boolean },
  ): Promise<{ ok: boolean; error?: string }>;
  saveFileDialog?(options?: {
    defaultPath?: string;
    filters?: Array<{ name: string; extensions: string[] }>;
  }): Promise<{ canceled: boolean; filePath?: string }>;
  startTunnel(): Promise<string>;
  stopTunnel(): Promise<void>;
  getTunnelUrl(): Promise<string | null>;
  getCdpBrowsers?(): Promise<CdpBrowserInfo[]>;
  launchCdpBrowser?(): Promise<{ port?: number; error?: string; id?: string }>;
  connectCdpBrowser?(port: number): Promise<{ success?: boolean; error?: string }>;
  removeCdpBrowser?(id: string): Promise<{ success: boolean; error?: string }>;
  onCdpPoolChanged?(cb: (browsers: CdpBrowserInfo[]) => void): () => void;
  checkForUpdates?(): Promise<{ ok: boolean; message: string }>;
  getKeepAwake?(): Promise<{ enabled: boolean; supported: boolean }>;
  setKeepAwake?(input: { enabled: boolean }): Promise<{
    ok: boolean;
    enabled: boolean;
    error?: string;
  }>;
}

declare global {
  interface Window {
    api: ElectronAPI;
  }
}

export {};
