/**
 * Parse chat `[附件: path1, path2]` markers for display (backend keeps full paths).
 */

import { decodeUnicodeEscapes, fileBasename } from "@/lib/fsPath";

const ATTACHMENT_RE = /\[附件:\s*([^\]]+)\]/g;

export function fileNameFromPath(path: string): string {
  // Decode \uXXXX BEFORE treating `\` as a separator (otherwise
  // `...\u6790.png` becomes basename `u6790.png`).
  return fileBasename(path) || decodeUnicodeEscapes(path);
}

export function parseUserAttachments(content: string): {
  text: string;
  paths: string[];
} {
  const paths: string[] = [];
  const src = content || "";
  for (const match of src.matchAll(ATTACHMENT_RE)) {
    for (const part of match[1].split(",")) {
      const p = part.trim().replace(/^["']|["']$/g, "");
      if (p && !paths.includes(p)) paths.push(p);
    }
  }
  const text = src
    .replace(ATTACHMENT_RE, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return { text, paths };
}

/** Session sidebar title: prefer query text, else first attachment name. */
export function displayTitleFromUserContent(content: string, maxLen = 40): string {
  const { text, paths } = parseUserAttachments(content);
  const base = text || (paths[0] ? fileNameFromPath(paths[0]) : "");
  if (!base) return "任务中";
  return base.length > maxLen ? base.slice(0, maxLen) : base;
}
