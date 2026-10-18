/** Format token counts for live usage UI (e.g. 1,234 / 12.3万). */

export const DEFAULT_CONTEXT_LIMIT = 0; // Unknown until the model profile is available.

export function formatTokenCount(n: number): string {
  const v = Math.max(0, Math.floor(Number(n) || 0));
  if (v >= 100_000) {
    const wan = v / 10_000;
    return `${wan >= 100 ? wan.toFixed(0) : wan.toFixed(1).replace(/\.0$/, "")}万`;
  }
  return v.toLocaleString("zh-CN");
}

export function formatTokenUsage(tokens: number, maxTokens?: number): string {
  const used = formatTokenCount(tokens);
  if (maxTokens != null && maxTokens > 0) {
    return `${used} / ${formatTokenCount(maxTokens)} tokens`;
  }
  return `${used} tokens`;
}

/** WorkBuddy-style compact counts: ``98.2K`` / ``192.0K``. */
export function formatTokenK(n: number): string {
  const v = Math.max(0, Number(n) || 0);
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v < 1000) return String(Math.round(v));
  return `${(v / 1000).toFixed(1)}K`;
}

export function formatContextUsedStats(used: number, limit: number): string {
  if (!Number.isFinite(limit) || limit <= 0) return `约 ${formatTokenK(used)} tokens · 上下文窗口未知`;
  const denom = limit;
  const pct = denom > 0 ? Math.min(100, (Math.max(0, used) / denom) * 100) : 0;
  return `${pct.toFixed(1)}% · ${formatTokenK(used)} / ${formatTokenK(denom)}`;
}

export function formatContextUsedLabel(used: number, limit: number): string {
  if (!Number.isFinite(limit) || limit <= 0) return formatContextUsedStats(used, limit);
  return `${formatContextUsedStats(used, limit)} 上下文已使用`;
}

export function estimateTokensFromText(text: string): number {
  if (!text) return 0;
  let cjk = 0;
  let other = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0) ?? 0;
    if (cp >= 0x4e00 && cp <= 0x9fff) cjk += 1;
    else other += 1;
  }
  return Math.max(0, Math.ceil(cjk / 1.5 + other / 4));
}

export function estimateSessionContextTokens(
  messages: Array<{ content?: string }>,
  draft = "",
): number {
  let blob = draft;
  for (const m of messages) blob += m.content || "";
  return estimateTokensFromText(blob);
}

export function resolveContextUsage(opts: {
  messages?: Array<{ content?: string }>;
  draft?: string;
  contextTokens?: number;
  contextLimit?: number;
  budgetMaxTokens?: number;
}): { used: number; limit: number; percentage: number } {
  const limit =
    opts.contextLimit && opts.contextLimit > 0
      ? opts.contextLimit
      : DEFAULT_CONTEXT_LIMIT;
  const estimated = estimateSessionContextTokens(opts.messages ?? [], opts.draft ?? "");
  // Full chat history survives compaction; it must not override a smaller
  // effective prompt reported by the backend after summarization.
  const used = opts.contextTokens != null && opts.contextTokens >= 0
    ? opts.contextTokens + estimateTokensFromText(opts.draft ?? '') : estimated;
  const percentage = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  return { used, limit, percentage };
}
