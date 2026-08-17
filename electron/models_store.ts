/**
 * Persisted model profiles (provider + model id + optional base URL).
 * API keys live in the keychain under account ``model:<id>``.
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
}

export interface ModelsState {
  profiles: ModelProfile[];
  activeId: string | null;
}

const EMPTY: ModelsState = { profiles: [], activeId: null };

let _filePath = "";

export function initModelsStore(userDataPath: string): void {
  _filePath = path.join(userDataPath, "models.json");
}

export function loadModels(): ModelsState {
  if (!_filePath) return { ...EMPTY, profiles: [] };
  try {
    const raw = JSON.parse(fs.readFileSync(_filePath, "utf8")) as ModelsState;
    return {
      profiles: Array.isArray(raw.profiles) ? raw.profiles : [],
      activeId: raw.activeId ?? null,
    };
  } catch {
    return { profiles: [], activeId: null };
  }
}

export function saveModels(state: ModelsState): void {
  if (!_filePath) return;
  fs.mkdirSync(path.dirname(_filePath), { recursive: true });
  fs.writeFileSync(_filePath, JSON.stringify(state, null, 2), { mode: 0o600 });
}

export function getActiveProfile(): ModelProfile | null {
  const state = loadModels();
  if (!state.activeId) return null;
  return state.profiles.find((p) => p.id === state.activeId) ?? null;
}

export function upsertProfile(profile: ModelProfile): ModelsState {
  const state = loadModels();
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
