import type { ModelProvider, ModelCategory, ModelConnection, ModelProfile, ModelsState } from "../../electron/models_store";
export type { ModelProvider, ModelCategory, ModelConnection, ModelProfile, ModelsState, ReasoningSelection } from "../../electron/models_store";

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

export type UpdaterState =
  | "idle"
  | "checking"
  | "available"
  | "not-available"
  | "downloading"
  | "downloaded"
  | "error";

export interface UpdaterStatus {
  state: UpdaterState;
  currentVersion: string;
  availableVersion?: string;
  percent?: number;
  totalSize?: number;
  message?: string;
}

export interface IndustryStatus {
  busy: boolean;
  phase: string;
  appId?: string;
  message?: string;
  detail?: string;
  active?: number;
  tasks?: string[];
  generation?: string;
}

export interface ElectronAPI {
  getBackendUrl(): Promise<string>;
  backendRequest(id: string, request: { url: string; method?: string; headers?: Record<string, string>; body?: Uint8Array }): Promise<{ status: number; statusText: string; headers: Record<string, string> }>;
  backendRead(id: string): Promise<{ done: boolean; value?: Uint8Array }>;
  backendCancel(id: string): Promise<void>;
  restartBackend(): Promise<string>;
  industryStatus(): Promise<IndustryStatus>;
  industryCancel(): Promise<void>;
  onIndustryStatus(callback: (status: IndustryStatus) => void): () => void;
  industryList(): Promise<{
    lifecycle?: IndustryStatus;
    operation?: { id: string; phase: string; app_id: string; error?: string; retained?: string };
    apps: Array<{
      id: string;
      version: string | null;
      generation?: string;
      dev_revision?: string;
      dev_url?: string;
      candidate?: { version: string };
      recovery?: { snapshot: { created_at: string } };
      previous_version?: string | null;
      enabled: boolean;
      status: string;
      error?: string;
      manifest: { name: string; description: string; ui: { entry: string }; capabilities?: { host_api: string[] }; agent_tools?: Array<{ name: string; title: string; description: string; access: "read" | "write" }> };
    }>;
  }>;
  industryInspect(filePath: string): Promise<{
    skill_names?: string[];
    current_version?: string | null;
    previous_tools?: Array<{ name: string; title: string; access: string }>;
    sha256: string;
    file_count: number;
    expanded_bytes: number;
    trusted_code: boolean;
    manifest: { id: string; name: string; version: string; description: string; capabilities: { host_api: string[] }; agent_tools?: Array<{ name: string; title: string; description: string; access: "read" | "write" }> };
  }>;
  industryInstall(filePath: string, expectedSha256: string): Promise<{
    id: string;
    version: string;
    requires_restart: boolean;
  }>;
  industryRequest(appId: string, method: string, requestPath: string, body?: unknown, generation?: string): Promise<unknown>;
  industryManage(appId: string, action: "disable" | "enable" | "rollback" | "remove" | "retry"): Promise<unknown>;
  getKey(account: string): Promise<string | null>;
  setKey(account: string, value: string): Promise<void>;
  getModelCatalog(): Promise<import("../../electron/model_capabilities").ModelCatalog>;
  refreshModelCatalog(): Promise<import("../../electron/model_capabilities").ModelCatalog>;
  onModelCatalogChanged?(cb: () => void): () => void;
  getModels(): Promise<ModelsState>;
  upsertConnection(input: ModelConnection & { apiKey?: string }): Promise<ModelsState>;
  removeConnection(id: string): Promise<ModelsState>;
  setCompactionRatio(ratio: number): Promise<ModelsState>;
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
    connectionId?: string;
    capabilityId?: string;
    reasoningAdapter?: string;
    reasoning?: ModelProfile["reasoning"];
    contextWindow?: number;
  }): Promise<ModelsState>;
  removeModel(id: string): Promise<ModelsState>;
  setActiveModel(id: string): Promise<ModelsState>;
  validateModel?(input: {
    profileId?: string;
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
  onBackendReady?(cb: (url: string) => void): () => void;
  onBackendStarting?(cb: () => void): () => void;
  onBackendFailed?(cb: (message: string) => void): () => void;
  onBackendNeedsModel?(cb: () => void): () => void;
  getBackendStatus?(): Promise<{
    state: "starting" | "ready" | "needs-model" | "failed";
    error: string;
  }>;
  getUpdaterStatus?(): Promise<UpdaterStatus>;
  checkForUpdates?(): Promise<UpdaterStatus>;
  downloadUpdate?(): Promise<UpdaterStatus>;
  installUpdate?(): Promise<{ ok: boolean; message?: string }>;
  onUpdaterStatus?(cb: (status: UpdaterStatus) => void): () => void;
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
