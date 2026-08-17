import anthropicImage from "@/assets/model/anthropic.svg";
import deepseekImage from "@/assets/model/deepseek.svg";
import lmstudioImage from "@/assets/model/lmstudio.svg";
import minimaxImage from "@/assets/model/minimax.svg";
import moonshotImage from "@/assets/model/moonshot.svg";
import ollamaImage from "@/assets/model/ollama.svg";
import openaiImage from "@/assets/model/openai.svg";
import openrouterImage from "@/assets/model/openrouter.svg";
import qwenImage from "@/assets/model/qwen.svg";
import vllmImage from "@/assets/model/vllm.svg";
import zaiImage from "@/assets/model/zai.svg";

const MODEL_PROVIDER_IMAGE_MAP: Record<string, string> = {
  openai: openaiImage,
  anthropic: anthropicImage,
  openrouter: openrouterImage,
  "tongyi-qianwen": qwenImage,
  deepseek: deepseekImage,
  minimax: minimaxImage,
  "z.ai": zaiImage,
  moonshot: moonshotImage,
  "openai-compatible-model": openaiImage,
  ollama: ollamaImage,
  vllm: vllmImage,
  lmstudio: lmstudioImage,
  "local-ollama": ollamaImage,
  "local-vllm": vllmImage,
  "local-lmstudio": lmstudioImage,
};

/** Logos that use dark fills and need inversion in dark mode. */
export const DARK_FILL_MODELS = new Set([
  "openai",
  "anthropic",
  "moonshot",
  "ollama",
  "openrouter",
  "lmstudio",
  "z.ai",
  "openai-compatible-model",
]);

/** Resolve provider / preset id to a logo URL for dropdowns and sidebars. */
export function getModelImage(modelId: string | null | undefined): string | null {
  if (!modelId) return null;
  return MODEL_PROVIDER_IMAGE_MAP[modelId] ?? null;
}

/** Whether a logo should be inverted in dark mode (fill-style logos). */
export function needsInvertModelImage(
  modelId: string | null | undefined,
  appearance: string | undefined,
): boolean {
  if (!modelId || appearance !== "dark") return false;
  const key = modelId.startsWith("local-")
    ? modelId.replace("local-", "")
    : modelId;
  return DARK_FILL_MODELS.has(key);
}

export function isDarkAppearance(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}
