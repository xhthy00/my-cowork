/** Schedule jobs list (backed by skill schedules). */
import { useEffect, useState } from "react";

interface JobRow {
  id: string;
  schedule?: string | null;
  name: string;
  enabled: boolean;
}

export default function ScheduleView() {
  const [jobs, setJobs] = useState<JobRow[]>([]);

  useEffect(() => {
    void (async () => {
      const backendUrl = await window.api.getBackendUrl();
      if (!backendUrl) return;
      const res = await fetch(`${backendUrl}/api/skills`);
      if (!res.ok) return;
      const data = (await res.json()) as {
        skills: Array<{ id: string; name: string; schedule?: string; enabled: boolean }>;
      };
      setJobs(
        (data.skills || [])
          .filter((s) => s.schedule)
          .map((s) => ({
            id: s.id,
            name: s.name,
            schedule: s.schedule,
            enabled: s.enabled,
          })),
      );
    })();
  }, []);

  return (
    <section className="view-page">
      <div className="view-header">
        <h2>定时任务</h2>
      </div>
      <table className="sched-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>Cron</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td>{j.name}</td>
              <td>
                <code>{j.schedule}</code>
              </td>
              <td>{j.enabled ? "启用" : "停用"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
