/**
 * Adapted from eigent: Folder/FolderComponent.tsx — sanitize office/csv HTML.
 */
import DOMPurify from "dompurify";
import { useMemo } from "react";

import { injectFontStyles } from "@/lib/htmlFontStyles";

export default function OfficeHtmlPreview({
  content,
}: {
  content: string | null | undefined;
}) {
  const sanitizedHtml = useMemo(() => {
    const raw = content || "";
    if (!raw) return "";

    const dangerousPatterns = [
      /ipcRenderer/gi,
      /require\s*\(\s*['"`]electron['"`]\s*\)/gi,
      /nodeIntegration/gi,
    ];
    for (const pattern of dangerousPatterns) {
      if (pattern.test(raw)) return "";
    }

    const sanitized = DOMPurify.sanitize(raw, {
      USE_PROFILES: { html: true },
      ALLOWED_TAGS: [
        "a",
        "b",
        "i",
        "u",
        "strong",
        "em",
        "p",
        "br",
        "ul",
        "ol",
        "li",
        "img",
        "div",
        "span",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "pre",
        "code",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "style",
        "hr",
      ],
      ALLOWED_ATTR: [
        "href",
        "src",
        "alt",
        "title",
        "width",
        "height",
        "target",
        "rel",
        "colspan",
        "rowspan",
        "class",
        "id",
        "style",
      ],
      FORBID_TAGS: ["script", "iframe", "object", "embed", "form", "input", "button"],
      SANITIZE_DOM: true,
      KEEP_CONTENT: false,
    });
    return injectFontStyles(sanitized);
  }, [content]);

  return (
    <div
      className="h-full w-full overflow-auto text-ds-text-neutral-default-default"
      dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
    />
  );
}
