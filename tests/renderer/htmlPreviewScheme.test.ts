import { describe, expect, it } from "vitest";

import {
  isLocalPreviewUrl,
  LOCAL_HTML_PREVIEW_COLOR_SCHEME_CSS,
} from "../../renderer/src/lib/htmlPreviewScheme";

describe("htmlPreviewScheme", () => {
  it("treats localfile and file URLs as local documents", () => {
    expect(isLocalPreviewUrl("localfile://c/Users/me/a.html")).toBe(true);
    expect(isLocalPreviewUrl("file:///C:/Users/me/a.html")).toBe(true);
    expect(isLocalPreviewUrl("https://example.com")).toBe(false);
  });

  it("forces light color-scheme without overriding author backgrounds", () => {
    expect(LOCAL_HTML_PREVIEW_COLOR_SCHEME_CSS).toContain("color-scheme: light");
    expect(LOCAL_HTML_PREVIEW_COLOR_SCHEME_CSS).not.toMatch(
      /background[^;]*!important/,
    );
  });
});
