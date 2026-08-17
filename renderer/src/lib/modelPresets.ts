import type { ModelCategory, ModelProvider } from "../window";

export interface ModelPreset {
  /** Stable id for logos / sidebar tabs (Eigent-aligned). */
  id: string;
  name: string;
  provider: ModelProvider;
  category: ModelCategory;
  defaultHost: string;
  /** Alternate hosts that still map to this preset (e.g. regional endpoints). */
  altHosts?: string[];
  /** Suggested model id placeholder (empty = user must fill / pick). */
  defaultModel: string;
  /** Local providers may omit API key. */
  requiresApiKey: boolean;
  /** Relative path used to list models from the host. */
  fetchPath?: string;
  parseModels?: (data: unknown) => string[];
}

const parseOllamaModels = (data: unknown): string[] => {
  const models = (data as { models?: Array<{ name?: string }> })?.models;
  return (models ?? []).map((m) => m.name).filter((n): n is string => !!n);
};

const parseOpenAICompatibleModels = (data: unknown): string[] => {
  const rows = (data as { data?: Array<{ id?: string }> })?.data;
  return (rows ?? []).map((m) => m.id).filter((id): id is string => !!id);
};

function normalizeHost(url: string): string {
  return url.trim().replace(/\/+$/, "").toLowerCase();
}

function hostMatches(profileUrl: string | undefined, candidates: string[]): boolean {
  if (!profileUrl) return false;
  const a = normalizeHost(profileUrl);
  return candidates.some((c) => {
    const b = normalizeHost(c);
    if (a === b) return true;
    // Treat missing/extra /v1 as equivalent.
    if (a.replace(/\/v1$/, "") === b.replace(/\/v1$/, "")) return true;
    try {
      return new URL(a).hostname === new URL(b).hostname;
    } catch {
      return false;
    }
  });
}

/** BYOK cloud providers (Custom tab) — subset of Eigent INIT_PROVODERS. */
export const BYOK_PRESETS: ModelPreset[] = [
  {
    id: "anthropic",
    name: "Anthropic",
    provider: "anthropic",
    category: "cloud_byok",
    defaultHost: "https://api.anthropic.com",
    defaultModel: "claude-sonnet-4-20250514",
    requiresApiKey: true,
  },
  {
    id: "openai",
    name: "OpenAI",
    provider: "openai_compat",
    category: "cloud_byok",
    defaultHost: "https://api.openai.com/v1",
    defaultModel: "gpt-4o-mini",
    requiresApiKey: true,
    fetchPath: "/models",
    parseModels: parseOpenAICompatibleModels,
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    provider: "openrouter",
    category: "cloud_byok",
    defaultHost: "https://openrouter.ai/api/v1",
    defaultModel: "openai/gpt-4o-mini",
    requiresApiKey: true,
    fetchPath: "/models",
    parseModels: parseOpenAICompatibleModels,
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    provider: "openai_compat",
    category: "cloud_byok",
    defaultHost: "https://api.deepseek.com",
    defaultModel: "deepseek-chat",
    requiresApiKey: true,
  },
  {
    id: "tongyi-qianwen",
    name: "通义千问",
    provider: "openai_compat",
    category: "cloud_byok",
    defaultHost: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    defaultModel: "qwen-plus",
    requiresApiKey: true,
  },
  {
    id: "moonshot",
    name: "Moonshot",
    provider: "openai_compat",
    category: "cloud_byok",
    defaultHost: "https://api.moonshot.ai/v1",
    defaultModel: "kimi-k2-turbo-preview",
    requiresApiKey: true,
  },
  {
    id: "minimax",
    name: "Minimax",
    provider: "openai_compat",
    category: "cloud_byok",
    // China endpoint first; keep international as alternate.
    defaultHost: "https://api.minimaxi.com/v1",
    altHosts: ["https://api.minimax.io/v1", "https://api.minimaxi.com"],
    defaultModel: "MiniMax-M2.5",
    requiresApiKey: true,
  },
  {
    id: "openai-compatible-model",
    name: "自定义兼容",
    provider: "openai_compat",
    category: "cloud_byok",
    defaultHost: "https://api.openai.com/v1",
    defaultModel: "",
    requiresApiKey: true,
    fetchPath: "/models",
    parseModels: parseOpenAICompatibleModels,
  },
];

/** Local host presets (Local tab). */
export const LOCAL_PRESETS: ModelPreset[] = [
  {
    id: "ollama",
    name: "Ollama",
    provider: "ollama",
    category: "local",
    defaultHost: "http://127.0.0.1:11434/v1",
    defaultModel: "",
    requiresApiKey: false,
    fetchPath: "/api/tags",
    parseModels: parseOllamaModels,
  },
  {
    id: "lmstudio",
    name: "LM Studio",
    provider: "lmstudio",
    category: "local",
    defaultHost: "http://127.0.0.1:1234/v1",
    defaultModel: "",
    requiresApiKey: false,
    fetchPath: "/models",
    parseModels: parseOpenAICompatibleModels,
  },
  {
    id: "vllm",
    name: "vLLM",
    provider: "vllm",
    category: "local",
    defaultHost: "http://127.0.0.1:8000/v1",
    defaultModel: "",
    requiresApiKey: false,
    fetchPath: "/models",
    parseModels: parseOpenAICompatibleModels,
  },
];

export const ALL_PRESETS: ModelPreset[] = [...BYOK_PRESETS, ...LOCAL_PRESETS];

export function findPreset(id: string | undefined | null): ModelPreset | undefined {
  if (!id) return undefined;
  return ALL_PRESETS.find((p) => p.id === id);
}

export interface ModelProfileLike {
  id: string;
  name: string;
  provider: string;
  model: string;
  baseUrl?: string;
  category?: string;
  presetId?: string;
}

/** Match a saved profile to a sidebar preset (tolerant of host/name drift). */
export function profileForPreset(
  profiles: ModelProfileLike[],
  preset: ModelPreset,
): ModelProfileLike | undefined {
  const byId = profiles.find((p) => p.presetId === preset.id);
  if (byId) return byId;

  const hosts = [preset.defaultHost, ...(preset.altHosts ?? [])];
  const byHost = profiles.find(
    (p) =>
      !p.presetId &&
      (p.provider === preset.provider ||
        (preset.provider !== "anthropic" && p.provider === "openai_compat")) &&
      hostMatches(p.baseUrl, hosts),
  );
  if (byHost) return byHost;

  // Legacy profiles saved without presetId: match display name.
  const nameLc = preset.name.toLowerCase();
  return profiles.find(
    (p) =>
      !p.presetId &&
      p.name.trim().toLowerCase() === nameLc &&
      (preset.category === "local"
        ? p.category === "local" ||
          p.provider === "ollama" ||
          p.provider === "lmstudio" ||
          p.provider === "vllm"
        : p.category !== "local"),
  );
}

/** Infer logo / preset id for a profile that may lack presetId. */
export function resolvePresetId(profile: ModelProfileLike): string | null {
  if (profile.presetId) return profile.presetId;
  for (const preset of ALL_PRESETS) {
    if (profileForPreset([profile], preset)?.id === profile.id) return preset.id;
  }
  return null;
}

/** Profiles that do not map to any known preset (still show in management). */
export function orphanProfiles(profiles: ModelProfileLike[]): ModelProfileLike[] {
  const claimed = new Set<string>();
  for (const preset of ALL_PRESETS) {
    const hit = profileForPreset(profiles, preset);
    if (hit) claimed.add(hit.id);
  }
  return profiles.filter((p) => !claimed.has(p.id));
}

/** Resolve list URL from base host + preset fetchPath. */
export function modelListUrl(baseUrl: string, preset: ModelPreset): string | null {
  if (!preset.fetchPath) return null;
  try {
    const base = new URL(baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
    if (preset.fetchPath.startsWith("/api/")) {
      return `${base.origin}${preset.fetchPath}`;
    }
    if (preset.fetchPath === "/models" || preset.fetchPath === "/v1/models") {
      const originPath = base.pathname.replace(/\/$/, "");
      if (originPath.endsWith("/v1") || preset.fetchPath === "/v1/models") {
        return `${base.origin}${originPath.endsWith("/v1") ? originPath : "/v1"}/models`;
      }
      return new URL("models", base).toString();
    }
    return new URL(preset.fetchPath.replace(/^\//, ""), base).toString();
  } catch {
    return null;
  }
}
