import { apiFetch } from "./backend";

export async function importSkillZip(file: File) {
  const backendUrl = await window.api.getBackendUrl();
  if (!backendUrl) throw new Error("后端未连接");
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const response = await apiFetch(`${backendUrl}/api/skills/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zip_base64: btoa(binary), filename: file.name }),
  });
  if (!response.ok) throw new Error(`导入失败 ${response.status}`);
}
