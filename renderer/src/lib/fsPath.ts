/** Decode literal `\uXXXX` escapes left in paths (JSON ensure_ascii / model text). */
export function decodeUnicodeEscapes(raw: string): string {
  let s = String(raw || "");
  // Run twice in case of double-escaped `\\uXXXX`
  for (let i = 0; i < 2; i++) {
    const next = s.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex: string) =>
      String.fromCharCode(parseInt(hex, 16)),
    );
    if (next === s) break;
    s = next;
  }
  return s;
}

/** Basename after decoding — never split on `\` inside `\uXXXX`. */
export function fileBasename(filePath: string): string {
  const normalized = decodeUnicodeEscapes(filePath).trim();
  if (!normalized) return "";
  // Real Windows separators remain as `\`; `\uXXXX` already decoded away.
  const parts = normalized.split(/[/\\]/);
  return parts[parts.length - 1] || normalized;
}

/** True when a stored display name was corrupted by splitting on `\u`. */
export function isCorruptBasename(name: string): boolean {
  const n = (name || "").trim();
  return /^u[0-9a-fA-F]{4}(\.|$)/i.test(n) || /\\u[0-9a-fA-F]{4}/i.test(n);
}

/** Normalize a stored/clicked file path for open/preview. */
export function normalizeFsPath(raw: string): string {
  return (
    decodeUnicodeEscapes(raw)
      .split(/[\r\n]+/)
      .map((p) => p.trim())
      .find(Boolean) || ""
  );
}
