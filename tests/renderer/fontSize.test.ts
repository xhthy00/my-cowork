/**
 * @vitest-environment jsdom
 */

import { afterEach, describe, expect, it } from "vitest";

import { APPEARANCE_STORAGE_KEY } from "../../renderer/src/lib/appearance";
import {
  applyDocumentFontSize,
  DEFAULT_FONT_SIZE_LEVEL,
  FONT_SIZE_SCALES,
  initFontSize,
  isFontSizeLevel,
  readStoredFontSize,
} from "../../renderer/src/lib/fontSize";

function resetFontSizeDom() {
  document.documentElement.style.removeProperty("--ui-font-scale");
  document.documentElement.removeAttribute("data-font-size");
}

describe("fontSize", () => {
  afterEach(() => {
    window.localStorage.removeItem(APPEARANCE_STORAGE_KEY);
    resetFontSizeDom();
  });

  it("treats missing or corrupt storage as default", () => {
    expect(readStoredFontSize()).toBe(DEFAULT_FONT_SIZE_LEVEL);
    window.localStorage.setItem(APPEARANCE_STORAGE_KEY, "{not-json");
    expect(readStoredFontSize()).toBe(DEFAULT_FONT_SIZE_LEVEL);
  });

  it("reads persisted level and applies the matching scale", () => {
    window.localStorage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({ state: { fontSize: 4 }, version: 0 }),
    );
    expect(readStoredFontSize()).toBe(4);
    applyDocumentFontSize(readStoredFontSize());
    expect(document.documentElement.getAttribute("data-font-size")).toBe("4");
    expect(document.documentElement.style.getPropertyValue("--ui-font-scale")).toBe(
      String(FONT_SIZE_SCALES[4]),
    );
  });

  it("initFontSize applies the stored level before render", () => {
    window.localStorage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({ state: { fontSize: 0 }, version: 0 }),
    );
    initFontSize();
    expect(document.documentElement.getAttribute("data-font-size")).toBe("0");
    expect(document.documentElement.style.getPropertyValue("--ui-font-scale")).toBe(
      String(FONT_SIZE_SCALES[0]),
    );
  });

  it("rejects out-of-range values", () => {
    expect(isFontSizeLevel(1)).toBe(true);
    expect(isFontSizeLevel(5)).toBe(false);
    expect(isFontSizeLevel("1")).toBe(false);
  });

  it("does not zoom the document (layout stays unscaled)", () => {
    applyDocumentFontSize(4);
    expect(document.documentElement.style.zoom).toBeFalsy();
  });
});
