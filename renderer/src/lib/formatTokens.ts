/** Format token counts for live usage UI (e.g. 1,234 / 12.3万). */

export const DEFAULT_CONTEXT_LIMIT = 200_000;

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
  if (v < 1000) return String(Math.round(v));
  return `${(v / 1000).toFixed(1)}K`;
}

export function formatContextUsedStats(used: number, limit: number): string {
  const denom = limit > 0 ? limit : DEFAULT_CONTEXT_LIMIT;
  const pct = denom > 0 ? Math.min(100, (Math.max(0, used) / denom) * 100) : 0;
  return `${pct.toFixed(1)}% · ${formatTokenK(used)} / ${formatTokenK(denom)}`;
}

export function formatContextUsedLabel(used: number, limit: number): string {
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
      : opts.budgetMaxTokens && opts.budgetMaxTokens > 0
        ? opts.budgetMaxTokens
        : DEFAULT_CONTEXT_LIMIT;
  const estimated = estimateSessionContextTokens(opts.messages ?? [], opts.draft ?? "");
  const used = Math.max(opts.contextTokens ?? 0, estimated);
  const percentage = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  return { used, limit, percentage };
}
