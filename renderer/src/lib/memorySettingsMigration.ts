const LEGACY_KEY = "my-cowork-memory-on";
const MIGRATED_KEY = "my-cowork-memory-setting-migrated";

/** Preserve an existing opt-out before the first post-upgrade chat request. */
export async function migrateLegacyMemorySetting(backendUrl: string): Promise<void> {
  try {
    if (localStorage.getItem(MIGRATED_KEY) === "1") return;
    if (localStorage.getItem(LEGACY_KEY) !== "0") return;
  } catch {
    return;
  }
  const response = await fetch(`${backendUrl}/api/memory/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: false }),
  });
  if (!response.ok) throw new Error("无法同步原有的记忆关闭设置");
  try { localStorage.setItem(MIGRATED_KEY, "1"); } catch { /* backend is authoritative */ }
}
