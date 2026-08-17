/**
 * Ported from AionUi (packages/desktop/src/renderer/components/Markdown/markdownUtils.ts).
 * Apache-2.0 © AionUi — adapted for my-cowork (no arco/icon-park deps).
 */
import type React from "react";

/**
 * Format raw code string, attempting JSON pretty-print.
 * Falls back to stripped trailing newline if parsing fails.
 */
export const formatCode = (code: string): string => {
  const content = String(code).replace(/\n$/, "");
  try {
    return JSON.stringify(JSON.parse(content), (_key, value) => value, 2);
  } catch {
    return content;
  }
};

/** Diff line background colors (AionUi diffColors, light + dark). */
const diffColors = {
  additionBgLight: "rgba(26, 127, 55, 0.12)",
  deletionBgLight: "rgba(207, 34, 46, 0.1)",
  hunkBgLight: "rgba(9, 105, 218, 0.1)",
  additionBgDark: "rgba(63, 185, 80, 0.18)",
  deletionBgDark: "rgba(248, 81, 73, 0.18)",
  hunkBgDark: "rgba(56, 139, 253, 0.18)",
};

/**
 * Get line background style for diff rendering.
 * Highlights additions (green), deletions (red), and hunk headers (blue).
 */
export const getDiffLineStyle = (line: string, isDark: boolean): React.CSSProperties => {
  if (line.startsWith("+") && !line.startsWith("+++")) {
    return { backgroundColor: isDark ? diffColors.additionBgDark : diffColors.additionBgLight };
  }
  if (line.startsWith("-") && !line.startsWith("---")) {
    return { backgroundColor: isDark ? diffColors.deletionBgDark : diffColors.deletionBgLight };
  }
  if (line.startsWith("@@")) {
    return { backgroundColor: isDark ? diffColors.hunkBgDark : diffColors.hunkBgLight };
  }
  return {};
};

/* ------------------------------------------------------------------ */
/* Local file link resolution (AionUi markdownUtils)                   */
/* ------------------------------------------------------------------ */

const safeDecodeURIComponent = (value: string): string => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

export type LocalFileLinkReference = {
  filePath: string;
  rawReference: string;
  line?: number;
  column?: number;
  endLine?: number;
};

type LocalFileLocation = {
  line?: number;
  column?: number;
  endLine?: number;
  source?: "hash" | "colon";
};

type LocalFilePathCandidate = {
  filePath: string;
  hashLocation?: LocalFileLocation;
  hasInvalidHash?: boolean;
};

const parseHashLocation = (hash: string): LocalFileLocation | null => {
  const match = /^#L(\d+)(?:-L(\d+))?$/.exec(hash);
  if (!match) return null;
  const [, lineText, endLineText] = match;
  return {
    line: Number(lineText),
    endLine: endLineText == null ? undefined : Number(endLineText),
    source: "hash",
  };
};

const splitHashLocation = (href: string): LocalFilePathCandidate => {
  const hashIndex = href.indexOf("#");
  if (hashIndex < 0) return { filePath: href };
  const hashLocation = parseHashLocation(href.slice(hashIndex));
  if (!hashLocation) {
    return { filePath: href.slice(0, hashIndex), hasInvalidHash: true };
  }
  return { filePath: href.slice(0, hashIndex), hashLocation };
};

const normalizeFilePath = (path: string): string => {
  return /^\/[A-Za-z]:[\\/]/.test(path) ? path.slice(1) : path;
};

const normalizeLocalFileHrefToPath = (href: string): LocalFilePathCandidate | null => {
  if (/^https?:\/\//i.test(href)) return null;

  if (/^file:/i.test(href)) {
    try {
      const url = new URL(href);
      const path = normalizeFilePath(safeDecodeURIComponent(url.pathname));
      const rawHash = safeDecodeURIComponent(url.hash);
      if (!rawHash) return { filePath: path };
      const hashLocation = parseHashLocation(rawHash);
      return hashLocation ? { filePath: path, hashLocation } : { filePath: path, hasInvalidHash: true };
    } catch {
      const stripped = href.replace(/^file:(?:\/\/)?/i, "");
      const candidate = splitHashLocation(stripped);
      return { ...candidate, filePath: normalizeFilePath(candidate.filePath) };
    }
  }

  const candidate = splitHashLocation(href);
  const path = candidate.filePath;

  if (/^[A-Za-z]:[\\/]/.test(path)) return { ...candidate, filePath: path };
  if (/^\/[A-Za-z]:[\\/]/.test(path)) return { ...candidate, filePath: path.slice(1) };
  if (/^\/(Users|home|tmp|private|var|mnt|Volumes)\//.test(path)) return candidate;
  if (/^\/[^/?#]+\/.+\.[^/?#/.]+$/.test(path)) return candidate;

  return null;
};

const splitLocationSuffix = (
  filePath: string,
): Omit<LocalFileLinkReference, "rawReference"> & LocalFileLocation => {
  const lineColumnMatch = /^(.*):(\d+):(\d+)$/.exec(filePath);
  if (lineColumnMatch) {
    const [, pathWithoutLocation, lineText, columnText] = lineColumnMatch;
    if (normalizeLocalFileHrefToPath(pathWithoutLocation)) {
      return {
        filePath: pathWithoutLocation,
        line: Number(lineText),
        column: Number(columnText),
        source: "colon",
      };
    }
  }

  const lineMatch = /^(.*):(\d+)$/.exec(filePath);
  if (!lineMatch) return { filePath };
  const [, pathWithoutLocation, lineText] = lineMatch;
  if (!normalizeLocalFileHrefToPath(pathWithoutLocation)) return { filePath };
  return { filePath: pathWithoutLocation, line: Number(lineText), source: "colon" };
};

const formatRawReference = (
  reference: Omit<LocalFileLinkReference, "rawReference">,
  source?: "hash" | "colon",
): string => {
  if (reference.line == null) return reference.filePath;
  if (source === "hash") {
    return `${reference.filePath}#L${reference.line}${reference.endLine == null ? "" : `-L${reference.endLine}`}`;
  }
  return `${reference.filePath}:${reference.line}${reference.column == null ? "" : `:${reference.column}`}`;
};

export const resolveLocalFileLinkReference = (
  rawHref: string,
  resolvedHref?: string,
): LocalFileLinkReference | null => {
  const href = safeDecodeURIComponent((rawHref || resolvedHref || "").trim());
  if (!href) return null;

  const candidate = normalizeLocalFileHrefToPath(href);
  if (!candidate || candidate.hasInvalidHash) return null;

  const colonReference = splitLocationSuffix(candidate.filePath);
  const reference =
    candidate.hashLocation?.line == null
      ? colonReference
      : { ...candidate.hashLocation, filePath: colonReference.filePath };

  if (!normalizeLocalFileHrefToPath(reference.filePath)) return null;

  const source = candidate.hashLocation?.line == null ? colonReference.source : "hash";
  const { source: _source, ...publicReference } = reference;
  return {
    ...publicReference,
    rawReference: formatRawReference(publicReference, source),
  };
};

export const resolveLocalFileLinkPath = (rawHref: string, resolvedHref?: string): string | null => {
  return resolveLocalFileLinkReference(rawHref, resolvedHref)?.filePath ?? null;
};

/* ------------------------------------------------------------------ */
/* LaTeX delimiter conversion (AionUi utils/chat/latexDelimiters.ts)   */
/* ------------------------------------------------------------------ */

/**
 * Convert LaTeX-style math delimiters to dollar-sign delimiters
 * that remark-math can process.
 *
 * \[...\] → $$...$$ (block display math)
 * \(...\) → $...$  (inline math)
 *
 * Content inside fenced code blocks (``` or ~~~) and inline code spans (`)
 * is preserved unchanged.
 */
export function convertLatexDelimiters(text: string): string {
  const segments: string[] = [];
  let pos = 0;

  const codeRegex = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)/g;

  let match;
  while ((match = codeRegex.exec(text)) !== null) {
    if (match.index > pos) {
      segments.push(replaceLatex(text.slice(pos, match.index)));
    }
    segments.push(match[0]);
    pos = match.index + match[0].length;
  }

  if (pos < text.length) {
    segments.push(replaceLatex(text.slice(pos)));
  }

  return segments.join("");
}

function replaceLatex(text: string): string {
  text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_m, content: string) => `$$${content}$$`);
  text = text.replace(/\\\(([\s\S]*?)\\\)/g, (_m, content: string) => `$${content}$`);
  return text;
}
