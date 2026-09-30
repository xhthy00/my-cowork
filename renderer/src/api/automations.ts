import { apiFetch as fetch } from "@/api/backend";
import { backendUnavailableMessage } from "@/lib/backendStatus";
export type Schedule = {
  kind: "cron" | "once" | "interval";
  cron?: string | null;
  fire_at?: string | null;
  interval_seconds?: number | null;
  timezone: string;
};

export type Automation = {
  id: string;
  title: string;
  instructions: string;
  schedule: Schedule;
  schedule_label: string;
  source: string;
  workspace?: string | null;
  space_id?: string | null;
  project_id?: string | null;
  assistant_id?: string | null;
  enabled: boolean;
  next_run: number | null;
  last_run: number | null;
  last_status: string | null;
  run_count: number;
  unseen_runs: number;
  unseen_failed: boolean;
  notify_on_completion: boolean;
  notify_target?: string | null;
  active_run?: AutomationRun | null;
  always_allowed_tools?: Array<{ tool: string; target: string }>;
  always_allowed_commands?: string[];
  auto_approve_commands?: boolean;
};

export type AutomationRun = {
  run_id: string;
  task_id: string;
  task_execution_id: string;
  session_id: string;
  trigger: string;
  started_at: number;
  finished_at: number | null;
  status: string;
  result_text: string;
  artifacts: string[];
  error: string | null;
  notification_error?: string | null;
  recovery_tools?: Array<{ tool: string; call_id: string }>;
};

export type RunEvent = Record<string, unknown> & { type?: string };

export async function automationApi<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await window.api.getBackendUrl();
  if (!base) throw new Error(await backendUnavailableMessage());
  const response = await fetch(`${base}/api/automations${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch { /* Retain status message. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
