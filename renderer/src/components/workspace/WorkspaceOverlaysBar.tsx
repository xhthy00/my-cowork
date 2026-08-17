/**
 * Pending overlay Apply/Discard for copy/worktree Projects.
 * Adapted from eigent WorkspaceProjectPicker overlay actions.
 */
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getActiveProjectContext, useSessionsStore } from "@/store/sessions";

interface OverlayRow {
  id: string;
  relative_path: string;
}

export default function WorkspaceOverlaysBar() {
  const activeId = useSessionsStore((s) => s.activeId);
  const project = useSessionsStore((s) =>
    s.sessions.find((x) => x.id === s.activeId),
  );
  const [overlays, setOverlays] = useState<OverlayRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const needsOverlay =
    project?.workdirMode === "copy" || project?.workdirMode === "worktree";

  const reload = useCallback(async () => {
    if (!needsOverlay || !project) {
      setOverlays([]);
      return;
    }
    try {
      const url = await window.api.getBackendUrl();
      if (!url) return;
      const res = await fetch(
        `${url}/api/workspace/${encodeURIComponent(project.spaceId)}/projects/${encodeURIComponent(project.id)}/overlays`,
      );
      if (!res.ok) return;
      const data = (await res.json()) as { overlays: OverlayRow[] };
      setOverlays(data.overlays || []);
    } catch {
      /* ignore */
    }
  }, [needsOverlay, project]);

  useEffect(() => {
    void reload();
    const t = setInterval(() => void reload(), 4000);
    return () => clearInterval(t);
  }, [reload, activeId]);

  if (!needsOverlay || overlays.length === 0) return null;

  async function applyAll() {
    if (!project) return;
    setBusy(true);
    setStatus("正在合入…");
    try {
      const url = await window.api.getBackendUrl();
      if (!url) return;
      const res = await fetch(
        `${url}/api/workspace/${encodeURIComponent(project.spaceId)}/projects/${encodeURIComponent(project.id)}/apply`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
      );
      const data = (await res.json()) as { applied?: string[]; errors?: string[] };
      setStatus(
        res.ok
          ? `已合入 ${data.applied?.length ?? 0} 个文件`
          : `合入失败`,
      );
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function discardAll() {
    if (!project) return;
    setBusy(true);
    try {
      const url = await window.api.getBackendUrl();
      if (!url) return;
      await fetch(
        `${url}/api/workspace/${encodeURIComponent(project.spaceId)}/projects/${encodeURIComponent(project.id)}/discard`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
      );
      setStatus("已丢弃待合入更改");
      await reload();
    } finally {
      setBusy(false);
    }
  }

  const { space } = getActiveProjectContext();

  return (
    <div className="mx-auto mb-2 flex w-full max-w-[600px] flex-col gap-2 rounded-xl border border-ds-border-neutral-default-default bg-ds-bg-neutral-default-default px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 text-xs text-ds-text-neutral-muted-default">
          <span className="font-semibold text-ds-text-neutral-default-default">
            {overlays.length} 个待合入更改
          </span>
          {space?.rootPath && (
            <span className="ml-2 truncate opacity-70">→ {space.rootPath}</span>
          )}
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => void discardAll()}
          >
            丢弃
          </Button>
          <Button
            type="button"
            size="sm"
            variant="primary"
            disabled={busy}
            onClick={() => void applyAll()}
          >
            合入 Space
          </Button>
        </div>
      </div>
      <ul className="max-h-20 overflow-y-auto text-[11px] text-ds-text-neutral-subtle-default">
        {overlays.slice(0, 8).map((o) => (
          <li key={o.id} className="truncate font-mono">
            {o.relative_path}
          </li>
        ))}
        {overlays.length > 8 && <li>…还有 {overlays.length - 8} 个</li>}
      </ul>
      {status && (
        <p className="text-[11px] text-ds-text-neutral-subtle-default">{status}</p>
      )}
    </div>
  );
}
