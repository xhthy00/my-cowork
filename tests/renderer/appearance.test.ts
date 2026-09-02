/**
 * @vitest-environment jsdom
 */

import { afterEach, describe, expect, it } from "vitest";

import {
  APPEARANCE_STORAGE_KEY,
  applyDocumentAppearance,
  readDocumentTheme,
  readStoredAppearance,
  resolveDark,
} from "../../renderer/src/lib/appearance";

describe("appearance", () => {
  afterEach(() => {
    window.localStorage.removeItem(APPEARANCE_STORAGE_KEY);
    document.documentElement.classList.remove("dark");
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
  });

  it("reads zustand persist payload and applies dark class", () => {
    window.localStorage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({ state: { appearance: "dark" }, version: 0 }),
    );
    expect(readStoredAppearance()).toBe("dark");
    applyDocumentAppearance(readStoredAppearance());
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(readDocumentTheme()).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("treats missing or corrupt storage as system", () => {
    expect(readStoredAppearance()).toBe("system");
    window.localStorage.setItem(APPEARANCE_STORAGE_KEY, "{not-json");
    expect(readStoredAppearance()).toBe("system");
  });

  it("resolveDark honors explicit light/dark", () => {
    expect(resolveDark("light")).toBe(false);
    expect(resolveDark("dark")).toBe(true);
  });

  it("applyDocumentAppearance light clears dark class and data-theme", () => {
    applyDocumentAppearance("dark");
    applyDocumentAppearance("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(readDocumentTheme()).toBe("light");
  });
});
