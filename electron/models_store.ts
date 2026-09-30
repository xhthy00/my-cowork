/**
 * Persisted model profiles (provider + model id + optional base URL).
 * API keys use connection credential references; migration preserves legacy accounts.
 */

import * as fs from "fs";
import * as path from "path";

export type ModelProvider =
  | "anthropic"
  | "openai_compat"
  | "openrouter"
  | "ollama"
  | "lmstudio"
  | "vllm";

export type ModelCategory = "cloud_byok" | "local";

export interface ModelConnection {
  id: string;
  name: string;
  provider: ModelProvider;
  baseUrl?: string;
  category?: ModelCategory;
  presetId?: string;
  /** Stable credential reference. Migration keeps the original encrypted entry. */
  keyAccount?: string;
}

export interface ReasoningSelection {
  effort?: string;
  enabled?: boolean;
  budgetTokens?: number;
}

export interface ModelProfile {
  id: string;
  name: string;
  provider: ModelProvider;
  model: string;
  baseUrl?: string;
  isValid?: boolean;
  lastValidatedAt?: string;
  category?: ModelCategory;
  /** Maps to logo / sidebar preset id (e.g. openrouter, local-ollama). */
  presetId?: string;
  connectionId?: string;
  capabilityId?: string;
  reasoningAdapter?: string;
  reasoning?: ReasoningSelection;
  contextWindow?: number;
}

export interface ModelsState {
  profiles: ModelProfile[];
  activeId: string | null;
  connections?: ModelConnection[];
  compactionRatio?: number;
}

const EMPTY: ModelsState = { profiles: [], activeId: null };

let _filePath = "";

export function initModelsStore(userDataPath: string): void {
  _filePath = path.join(userDataPath, "models.json");
}

export function loadModels(): ModelsState {
  if (!_filePath) return { ...EMPTY, profiles: [] };
  if (!fs.existsSync(_filePath)) return { profiles: [], activeId: null, connections: [] };
  const raw = JSON.parse(fs.readFileSync(_filePath, "utf8")) as ModelsState;
  if (!Array.isArray(raw.profiles)) throw new Error("模型配置文件损坏，请恢复备份后重试");
  const connections = [...(raw.connections ?? [])];
  const profiles = raw.profiles.map((profile) => {
    const connectionId = profile.connectionId ?? `legacy-${profile.id}`;
    let connection = connections.find(c => c.id === connectionId);
    if (!connection) {
      if (profile.connectionId) throw new Error("模型引用的服务连接不存在");
      connection = { id: connectionId, name: profile.name, provider: profile.provider,
        baseUrl: profile.baseUrl, category: profile.category, presetId: profile.presetId,
        keyAccount: `model:${profile.id}` };
      connections.push(connection);
    }
    return { ...profile, connectionId, provider: connection.provider, baseUrl: connection.baseUrl,
      category: connection.category, presetId: connection.presetId };
  });
  return { profiles, connections, activeId: raw.activeId ?? null, compactionRatio: raw.compactionRatio ?? 0.8 };
}

export function saveModels(state: ModelsState): void {
  if (!_filePath) return;
  fs.mkdirSync(path.dirname(_filePath), { recursive: true });
  const temporary = `${_filePath}.tmp`;
  fs.writeFileSync(temporary, JSON.stringify(state, null, 2), { mode: 0o600 });
  fs.renameSync(temporary, _filePath);
}

export function getActiveProfile(): ModelProfile | null {
  const state = loadModels();
  if (!state.activeId) return null;
  return state.profiles.find((p) => p.id === state.activeId) ?? null;
}

export function upsertProfile(profile: ModelProfile): ModelsState {
  const state = loadModels();
  if (!profile.id || !profile.model.trim()) throw new Error("请填写模型 ID");
  if (profile.connectionId && !state.connections?.some(c => c.id === profile.connectionId)) {
    throw new Error("服务连接不存在");
  }
  const idx = state.profiles.findIndex((p) => p.id === profile.id);
  if (idx >= 0) {
    state.profiles[idx] = profile;
  } else {
    state.profiles.push(profile);
  }
  if (!state.activeId) {
    state.activeId = profile.id;
  }
  saveModels(state);
  return loadModels();
}

export function validateConnection(connection: ModelConnection): void {
  if (!connection.id || !connection.name.trim()) throw new Error("请填写连接名称");
  if (!["anthropic", "openai_compat", "openrouter", "ollama", "lmstudio", "vllm"].includes(connection.provider)) throw new Error("连接协议无效");
  if (connection.baseUrl) {
    const url = new URL(connection.baseUrl);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error("请输入有效的 HTTP(S) 服务地址，密钥请单独保存");
  }
}

export function upsertConnection(connection: ModelConnection): ModelsState {
  validateConnection(connection);
  const state = loadModels();
  const connections = state.connections ?? [];
  const previous = connections.find(c => c.id === connection.id);
  const next = { ...connection, name: connection.name.trim(),
    keyAccount: previous?.keyAccount ?? `connection:${connection.id}` };
  state.connections = [...connections.filter(c => c.id !== connection.id), next];
  saveModels(state);
  return loadModels();
}

export function removeConnection(id: string): ModelsState {
  const state = loadModels();
  state.connections = state.connections?.filter(c => c.id !== id);
  state.profiles = state.profiles.filter(p => p.connectionId !== id);
  if (!state.profiles.some(p => p.id === state.activeId)) state.activeId = state.profiles[0]?.id ?? null;
  saveModels(state);
  return state;
}

export function setCompactionRatio(ratio: number): ModelsState {
  if (!Number.isFinite(ratio) || ratio < 0.1 || ratio > 0.95) throw new Error("压缩比例须为10%到95%");
  const state = loadModels();
  state.compactionRatio = ratio;
  saveModels(state);
  return state;
}

export function removeProfile(id: string): ModelsState {
  const state = loadModels();
  state.profiles = state.profiles.filter((p) => p.id !== id);
  if (state.activeId === id) {
    state.activeId = state.profiles[0]?.id ?? null;
  }
  saveModels(state);
  return state;
}

export function setActiveId(id: string): ModelsState {
  const state = loadModels();
  if (!state.profiles.some((p) => p.id === id)) {
    throw new Error(`Unknown model profile: ${id}`);
  }
  state.activeId = id;
  saveModels(state);
  return state;
}

/** Map UX provider ids to backend MY_COWORK_PROVIDER values. */
export function toBackendProvider(provider: ModelProvider): "anthropic" | "openai_compat" {
  if (provider === "anthropic") return "anthropic";
  return "openai_compat";
}
