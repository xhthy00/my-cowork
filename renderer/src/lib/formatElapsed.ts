/**
 * Adapted from eigent: ChatBox/MessageItem/TokenUtils.tsx — formatSplittingElapsed
 * Examples: "0s", "45s", "1m 05s", "12m 00s"
 */
export function formatSplittingElapsed(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "0秒";
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}秒`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}分 ${s.toString().padStart(2, "0")}秒`;
}
