import { useEffect, useState } from "react";

import KeepAwakeBanner, { openKeepAwakeSettings } from "@/components/settings/KeepAwakeBanner";
import { Button } from "@/components/ui/button";
import { SettingsField } from "@/components/settings/SettingsField";

interface JobRow {
  id: string;
  skill_id: string;
  schedule: string;
  enabled: boolean;
}

export default function ScheduleView() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [status, setStatus] = useState("");
  const [skillId, setSkillId] = useState("");
  const [cron, setCron] = useState("every 1 hours");

  async function load() {
    const backendUrl = await window.api.getBackendUrl();
    if (!backendUrl) {
      setStatus("后端离线");
      return;
    }
    const res = await fetch(`${backendUrl}/api/schedule/jobs`);
    if (!res.ok) {
      setStatus(`加载失败 ${res.status}`);
      return;
    }
    try {
      const data = (await res.json()) as { jobs?: JobRow[] };
      setJobs(data.jobs || []);
      setStatus("");
    } catch {
      setJobs([]);
      setStatus("");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="flex w-full flex-col items-start justify-between">
      <div className="mb-4 flex w-full items-center justify-between border-x-0 border-b-[0.5px] border-t-0 border-solid border-ds-border-neutral-default-default px-3 py-2">
        <div className="text-body-base font-bold text-ds-text-neutral-default-default">
          定时任务
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
          刷新
        </Button>
      </div>
      <div className="flex w-full flex-col gap-4 px-3">
        <KeepAwakeBanner
          className="mb-0"
          message="定时任务仅在电脑唤醒状态下运行。可在设置 → 通用打开「保持唤醒」。"
          onOpenKeepAwake={openKeepAwakeSettings}
        />
        {status ? (
          <p className="text-body-sm text-ds-text-neutral-muted-default">{status}</p>
        ) : null}
        <div className="w-full rounded-2xl bg-ds-bg-neutral-subtle-default px-6 py-5">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[160px] flex-1">
              <SettingsField
                title="技能 ID"
                value={skillId}
                onChange={(e) => setSkillId(e.target.value)}
                placeholder="我的技能"
              />
            </div>
            <div className="min-w-[180px] flex-1">
              <SettingsField
                title="调度表达式"
                value={cron}
                onChange={(e) => setCron(e.target.value)}
              />
            </div>
            <Button
              type="button"
              className="mb-[2px]"
              onClick={async () => {
                const backendUrl = await window.api.getBackendUrl();
                if (!backendUrl || !skillId.trim()) return;
                const res = await fetch(`${backendUrl}/api/schedule/jobs`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ skill_id: skillId.trim(), schedule: cron.trim() }),
                });
                setStatus(res.ok ? "已创建" : `失败 ${res.status}`);
                await load();
              }}
            >
              创建
            </Button>
          </div>
        </div>
        <div className="w-full overflow-hidden rounded-2xl bg-ds-bg-neutral-subtle-default px-6 py-5">
          <table className="w-full text-left text-body-sm">
            <thead>
              <tr className="border-b border-ds-border-neutral-subtle-default text-ds-text-neutral-muted-default">
                <th className="py-2 font-medium">任务</th>
                <th className="font-medium">Cron</th>
                <th className="font-medium">状态</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-b border-ds-border-neutral-subtle-default last:border-b-0">
                  <td className="py-2.5 font-medium text-ds-text-neutral-default-default">
                    {j.skill_id}
                  </td>
                  <td className="font-mono text-xs text-ds-text-neutral-muted-default">
                    {j.schedule}
                  </td>
                  <td>{j.enabled ? "开启" : "关闭"}</td>
                  <td className="space-x-2 py-2 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      type="button"
                      onClick={async () => {
                        const backendUrl = await window.api.getBackendUrl();
                        if (!backendUrl) return;
                        await fetch(
                          `${backendUrl}/api/schedule/jobs/${encodeURIComponent(j.id)}/run`,
                          { method: "POST" },
                        );
                      }}
                    >
                      运行
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      type="button"
                      onClick={async () => {
                        const backendUrl = await window.api.getBackendUrl();
                        if (!backendUrl) return;
                        await fetch(
                          `${backendUrl}/api/schedule/jobs/${encodeURIComponent(j.id)}`,
                          {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ enabled: !j.enabled }),
                          },
                        );
                        await load();
                      }}
                    >
                      {j.enabled ? "暂停" : "恢复"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!jobs.length ? (
            <p className="mt-3 text-body-sm text-ds-text-neutral-muted-default">
              暂无定时任务。可在上方创建，或在 skill.yaml 中声明 schedule。
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
