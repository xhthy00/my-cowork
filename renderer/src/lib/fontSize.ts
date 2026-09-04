import { APPEARANCE_STORAGE_KEY } from "./appearance";

export type FontSizeLevel = 0 | 1 | 2 | 3 | 4;

/** 小 → 默认 → … → 大。默认是第 2 档（index 1）。只放大字号，不 zoom 整页。 */
export const FONT_SIZE_SCALES = [0.875, 1, 1.125, 1.25, 1.375] as const;

export const DEFAULT_FONT_SIZE_LEVEL: FontSizeLevel = 1;

export function isFontSizeLevel(value: unknown): value is FontSizeLevel {
  return value === 0 || value === 1 || value === 2 || value === 3 || value === 4;
}

export function fontSizeScale(level: FontSizeLevel): number {
  return FONT_SIZE_SCALES[level];
}

export function readStoredFontSize(): FontSizeLevel {
  if (typeof localStorage === "undefined") return DEFAULT_FONT_SIZE_LEVEL;
  try {
    const raw = localStorage.getItem(APPEARANCE_STORAGE_KEY);
    if (!raw) return DEFAULT_FONT_SIZE_LEVEL;
    const parsed = JSON.parse(raw) as { state?: { fontSize?: unknown } };
    if (isFontSizeLevel(parsed?.state?.fontSize)) return parsed.state.fontSize;
  } catch {
    // Corrupt or unavailable storage — keep default.
  }
  return DEFAULT_FONT_SIZE_LEVEL;
}

export function applyDocumentFontSize(level: FontSizeLevel): void {
  const scale = fontSizeScale(level);
  document.documentElement.style.setProperty("--ui-font-scale", String(scale));
  document.documentElement.setAttribute("data-font-size", String(level));
}

export function initFontSize(): void {
  applyDocumentFontSize(readStoredFontSize());
}
