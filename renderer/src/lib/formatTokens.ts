/** Format token counts for live usage UI (e.g. 1,234 / 12.3万). */
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
