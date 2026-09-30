import { getProjectRuntime } from "../store/projectRuntime";

/** Eigent human-reply equivalent: answer the active question, not a new chat turn. */
export async function submitHumanReply(
  projectId: string,
  taskId: string,
  questionId: string,
  answer: string,
): Promise<void> {
  const value = answer.trim();
  if (!value) throw new Error("请输入回复内容");
  const backendUrl = (await window.api.getBackendUrl())?.trim();
  if (!backendUrl) throw new Error("后端未连接");
  const response = await fetch(
    `${backendUrl}/api/chat/${encodeURIComponent(taskId)}/human-reply`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: questionId, answer: value }),
    },
  );
  if (!response.ok) {
    if (response.status === 409) {
      getProjectRuntime(projectId).session.getState().cancelHumanQuestion(questionId);
    }
    throw new Error(response.status === 409 ? "该问题已失效，请重新发送任务" : "回复发送失败，请重试");
  }
  getProjectRuntime(projectId).session.getState().answerHumanQuestion(questionId, value);
}
