import type { Message } from "@/store/session";

export type Turn = { user: Message; assistants: Message[] };

/** Replies stay in persisted/model history, but share their question's UI card. */
export function groupTurns(messages: Message[]): Turn[] {
  const turns: Turn[] = [];
  let current: Turn | null = null;
  const questions = new Map<string, NonNullable<Message["humanQuestion"]>>();
  for (const message of messages) {
    if (message.role === "user") {
      const question = message.humanReplyTo ? questions.get(message.humanReplyTo)
        : [...questions.values()].reverse().find(question => question.status === "answered" && question.answer === message.content);
      if (question?.status === "answered" && question.answer === message.content && current) {
        questions.delete(question.question_id);
        continue;
      }
      questions.clear();
      current = { user: message, assistants: [] };
      turns.push(current);
    } else {
      if (!current) {
        current = { user: { id: `synthetic-${message.id}`, role: "user", content: "" }, assistants: [] };
        turns.push(current);
      }
      current.assistants.push(message);
      if (message.humanQuestion) questions.set(message.humanQuestion.question_id, message.humanQuestion);
    }
  }
  return turns;
}
