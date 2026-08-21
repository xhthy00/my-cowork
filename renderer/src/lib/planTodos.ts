/**
 * Client-side Progress seed while waiting for SSE.
 *
 * Eigent Single Agent does not pre-plan Progress. A fake "规划任务步骤"
 * row would occupy taskInfo, block live tool rows, and never complete if
 * the model skips todo_write. Leave Progress empty until todo_write /
 * to_sub_tasks / trace fallback.
 */
import type { TaskInfo } from "../types/workforce";

export function planTodosFromQuery(_text: string): TaskInfo[] {
  return [];
}
