import { expect, it } from "vitest";
import { commandSuggestions, parseChatCommand } from "../renderer/src/lib/chatCommands";
it("recognizes Chinese commands only at the leading complete token", () => {
  expect(parseChatCommand("/压缩 保留关于预算的讨论")).toEqual({ name: "压缩", argument: "保留关于预算的讨论" });
  expect(parseChatCommand("请执行 /压缩")).toBeNull();
  expect(parseChatCommand("/压缩文档.txt")).toBeNull();
  expect(commandSuggestions("/压")).toHaveLength(1);
  expect(commandSuggestions("/压缩 保留预算")).toHaveLength(0);
});
