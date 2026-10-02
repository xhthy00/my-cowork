import { expect, it } from "vitest";
import { groupTurns } from "../../renderer/src/components/chat/groupTurns";
import type { Message } from "../../renderer/src/store/session";

const question: Message = { id: "question", role: "assistant", content: "请补充", humanQuestion: {
  question_id: "q", task_id: "t", agent: "single", status: "answered", options: [], answer: "领导",
} };

it("merges a clarification reply into its question while preserving the final answer", () => {
  const messages: Message[] = [{ id: "ask", role: "user", content: "写邮件" }, question,
    { id: "reply", role: "user", content: "领导", humanReplyTo: "q" },
    { id: "result", role: "assistant", content: "邮件正文" }];
  const turns = groupTurns(messages);
  expect(turns).toHaveLength(1);
  expect(turns[0].assistants.map(message => message.id)).toEqual(["question", "result"]);
  expect(messages).toHaveLength(4); // Model/persisted history is unchanged.
});

it("also merges legacy replies without metadata, once only", () => {
  const turns = groupTurns([{ id: "ask", role: "user", content: "写邮件" }, question,
    { id: "reply", role: "user", content: "领导" },
    { id: "followup", role: "user", content: "领导" }]);
  expect(turns).toHaveLength(2);
  expect(turns[1].user.id).toBe("followup");
});

it("keeps unrelated, cancelled and orphan replies as normal messages", () => {
  expect(groupTurns([question, { id: "other", role: "user", content: "客户" }])).toHaveLength(2);
  expect(groupTurns([{ ...question, humanQuestion: { ...question.humanQuestion!, status: "cancelled" } },
    { id: "reply", role: "user", content: "领导" }])).toHaveLength(2);
  expect(groupTurns([{ id: "orphan", role: "user", content: "领导", humanReplyTo: "q" }])[0].user.id).toBe("orphan");
});

it("matches replies to concurrent questions by id rather than the latest question", () => {
  const second: Message = { ...question, id: "second", humanQuestion: { ...question.humanQuestion!, question_id: "q2", answer: "正式" } };
  const turns = groupTurns([{ id: "ask", role: "user", content: "写邮件" }, question, second,
    { id: "reply1", role: "user", content: "领导", humanReplyTo: "q" },
    { id: "reply2", role: "user", content: "正式", humanReplyTo: "q2" }]);
  expect(turns).toHaveLength(1);
  expect(turns[0].assistants).toHaveLength(2);
});
