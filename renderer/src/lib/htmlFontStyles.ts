/**
 * Adapted from eigent: lib/htmlFontStyles.ts (scoped fragment inject only).
 */
const SCOPED_FONT_STYLE = `<style data-eigent-fonts>
  .eigent-file-content *, .eigent-file-content *::before, .eigent-file-content *::after {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif !important;
  }
  .eigent-file-content code, .eigent-file-content pre, .eigent-file-content kbd, .eigent-file-content samp {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace !important;
  }
</style>`;

export function injectFontStyles(html: string): string {
  if (/<head[^>]*>/i.test(html) || /<html[^>]*>/i.test(html)) {
    return html;
  }
  return (
    SCOPED_FONT_STYLE + '<div class="eigent-file-content">' + html + "</div>"
  );
}
