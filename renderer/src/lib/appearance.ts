export type Appearance = "light" | "dark" | "system";

export const APPEARANCE_STORAGE_KEY = "my-cowork-settings";

export function isAppearance(value: unknown): value is Appearance {
  return value === "light" || value === "dark" || value === "system";
}

export function readStoredAppearance(): Appearance {
  if (typeof localStorage === "undefined") return "system";
  try {
    const raw = localStorage.getItem(APPEARANCE_STORAGE_KEY);
    if (!raw) return "system";
    const parsed = JSON.parse(raw) as { state?: { appearance?: unknown } };
    if (isAppearance(parsed?.state?.appearance)) return parsed.state.appearance;
  } catch {
    // Corrupt or unavailable storage — follow system.
  }
  return "system";
}

export function resolveDark(appearance: Appearance): boolean {
  if (appearance === "dark") return true;
  if (appearance === "light") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches === true;
}

export function applyDocumentAppearance(appearance: Appearance): void {
  const dark = resolveDark(appearance);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function initAppearance(): void {
  applyDocumentAppearance(readStoredAppearance());
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  mq?.addEventListener("change", () => {
    if (readStoredAppearance() === "system") applyDocumentAppearance("system");
  });
}
