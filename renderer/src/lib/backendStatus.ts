/** Shared offline copy for pages that require the local service. */
export async function backendUnavailableMessage(): Promise<string> {
  try {
    const status = await window.api.getBackendStatus?.();
    if (status?.state === "needs-model") return "尚未配置模型，请前往设置 → API / 模型完成配置";
    if (status?.state === "starting") return "本地服务正在启动，请稍候";
    if (status?.state === "failed") return `本地服务启动失败：${status.error || "请重试启动"}`;
  } catch { /* The bridge itself may be unavailable. */ }
  return "后端未连接，请检查本地服务或前往设置 → API / 模型";
}
