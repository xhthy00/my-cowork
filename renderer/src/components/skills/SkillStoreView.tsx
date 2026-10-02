import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/api/backend";
import SkillHubSuite from "./SkillHubSuite";
import { Button } from "@/components/ui/button";

export default function SkillStoreView() {
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("");

  const loadInstalled = useCallback(async () => {
    try {
      const backendUrl = await window.api.getBackendUrl();
      if (!backendUrl) return;
      const response = await apiFetch(`${backendUrl}/api/skills`);
      if (!response.ok) throw new Error(`读取已安装技能失败 (${response.status})`);
      const data = await response.json() as { skills?: { id: string }[] };
      setInstalledIds(new Set((data.skills || []).map(skill => skill.id)));
      setStatus("");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "读取已安装技能失败");
    }
  }, []);

  useEffect(() => {
    void loadInstalled();
    const backend = window.api.onBackendReady?.(() => { void loadInstalled(); });
    const industry = window.api.onIndustryStatus?.(state => { if (!state.busy) void loadInstalled(); });
    return () => { backend?.(); industry?.(); };
  }, [loadInstalled]);

  return <div className="skill-store-view w-full min-w-0">
    {status && <div role="status" className="mb-3 flex flex-wrap items-center gap-2 text-sm text-ds-text-neutral-muted-default">
      <span>{status}</span><Button size="sm" variant="ghost" onClick={() => void loadInstalled()}>重试</Button>
    </div>}
    <SkillHubSuite installedIds={installedIds} onInstalled={() => void loadInstalled()} />
  </div>;
}
