export const CHAT_COMMANDS = [{ name: "压缩", description: "压缩较早对话，可附加需要保留的内容", example: "/压缩 保留关于项目方案的讨论" }] as const;
export function parseChatCommand(text: string): { name: "压缩"; argument: string } | null {
  const match = text.trim().match(/^\/压缩(?:\s+([\s\S]*))?$/u);
  return match ? { name: "压缩", argument: (match[1] ?? "").trim() } : null;
}
export function commandSuggestions(text: string) {
  text = text.trim();
  if (!text.startsWith("/") || /\s/u.test(text)) return [];
  return CHAT_COMMANDS.filter(command => command.name.startsWith(text.slice(1)));
}
