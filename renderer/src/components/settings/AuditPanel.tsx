import { apiFetch as fetch } from "@/api/backend";
import { backendUnavailableMessage } from "@/lib/backendStatus";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useBackendEpoch } from "@/hooks/useBackendEpoch";
import { useSessionsStore } from "@/store/sessions";

type AuditEvent = {
  id: number;
  task_id: string;
  kind: string;
  tool: string;
  ok: boolean | null;
  at: number;
  detail: Record<string, unknown>;
};

export default function AuditPanel() {
  const activeId = useSessionsStore((state) => state.activeId);
  const [sessionId, setSessionId] = useState(activeId || "");
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { setSessionId(activeId || ""); }, [activeId]);
  async function refresh() {
    try {
      const url = await window.api.getBackendUrl();
      if (!url) throw new Error(await backendUnavailableMessage());
      const params = new URLSearchParams({ limit: "100" });
      if (sessionId.trim()) params.set("session_id", sessionId.trim());
      const response = await fetch(`${url}/api/audit?${params}`);
      if (!response.ok) throw new Error(`读取失败 (${response.status})`);
      const data = await response.json() as { events: AuditEvent[] };
      setEvents(data.events);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }
  const backendEpoch = useBackendEpoch();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on backend (re)start only; the filter refreshes on demand
  useEffect(() => { void refresh(); }, [backendEpoch]);
  return (
    <div className="px-3">
      <div className="mb-4 border-b border-ds-border-neutral-default-default px-3 py-2 font-bold">操作审计</div>
      <div className="rounded-2xl bg-ds-bg-neutral-subtle-default p-5">
        <p className="mb-4 text-sm text-ds-text-neutral-muted-default">查看最近的工具调用与确认记录。敏感参数已脱敏。</p>
        <div className="mb-4 flex gap-2">
          <input className="h-9 min-w-0 flex-1 rounded-lg bg-ds-bg-neutral-default-default px-3 text-sm outline-none" value={sessionId} onChange={(e) => setSessionId(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void refresh(); }} placeholder="按会话 ID 筛选（留空查看全部）" />
          <Button type="button" size="sm" onClick={() => void refresh()}>刷新</Button>
        </div>
        {error && <p className="mb-3 text-sm text-ds-text-error-default-default">{error}</p>}
        <div className="max-h-[560px] overflow-auto rounded-xl bg-ds-bg-neutral-default-default">
          {events.map((event) => (
            <div key={event.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-ds-border-neutral-subtle-default px-4 py-3 text-sm last:border-b-0">
              <span className="font-medium">{event.tool || event.kind}</span>
              <span className="text-ds-text-neutral-muted-default">{event.kind}</span>
              {event.ok !== null && <span>{event.ok ? "成功" : "失败"}</span>}
              <span className="ml-auto text-xs text-ds-text-neutral-muted-default">{new Date(event.at * 1000).toLocaleString()}</span>
              <span className="w-full truncate text-xs text-ds-text-neutral-muted-default" title={event.task_id}>任务 {event.task_id || "—"}</span>
            </div>
          ))}
          {!events.length && <div className="px-4 py-8 text-center text-sm text-ds-text-neutral-muted-default">暂无记录</div>}
        </div>
      </div>
    </div>
  );
}
