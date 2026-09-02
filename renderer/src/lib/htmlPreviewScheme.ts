/**
 * Local HTML deliverables are authored as light documents (dark ink, optional
 * white cards). The preview <webview> inherits the app's color-scheme:dark,
 * so Chromium paints a dark canvas while author CSS keeps color:#222 — unreadably
 * low contrast. Force light scheme only; do not override author backgrounds
 * (games / themed pages still paint their own).
 */
export const LOCAL_HTML_PREVIEW_COLOR_SCHEME_CSS = `
html { color-scheme: light; }
`.trim();

export function isLocalPreviewUrl(url: string): boolean {
  return /^(localfile:|file:)/i.test(url || "");
}
