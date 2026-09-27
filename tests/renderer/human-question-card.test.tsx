/** @vitest-environment jsdom */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import HumanQuestionCard from "../../renderer/src/components/chat/HumanQuestionCard";
import { getProjectRuntime } from "../../renderer/src/store/projectRuntime";
import { useSessionsStore } from "../../renderer/src/store/sessions";

const BACKEND_URL = "http://127.0.0.1:8000";
const question = {
  question_id: "question-1",
  task_id: "task-1",
  agent: "single_agent",
  options: ["PDF", "Word"],
  status: "pending" as const,
};

let originalFetch: typeof fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true }) as unknown as typeof fetch;
  window.api = { ...window.api, getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL) };
  useSessionsStore.setState({ activeId: "project-question-test" });
  getProjectRuntime("project-question-test").session.setState({
    messages: [{ id: "ask-message", role: "assistant", content: "选哪种格式？", humanQuestion: question }],
  });
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

it("submits an option as a reply to the original task", async () => {
  render(<HumanQuestionCard question={question} text="选哪种格式？" />);
  await userEvent.click(screen.getByRole("radio", { name: "Word" }));
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  await waitFor(() => {
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${BACKEND_URL}/api/chat/task-1/human-reply`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ question_id: "question-1", answer: "1. 请选择或自行填写：Word" }),
      }),
    );
  });
  const messages = getProjectRuntime("project-question-test").session.getState().messages;
  expect(messages[0].humanQuestion?.status).toBe("answered");
  expect(messages[1].content).toBe("1. 请选择或自行填写：Word");
});

it("accepts a custom answer instead of a suggested option", async () => {
  render(<HumanQuestionCard question={question} text="选哪种格式？" />);
  await userEvent.click(screen.getByRole("radio", { name: "自己填写" }));
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  expect(screen.getByRole("alert")).toHaveTextContent("请填写自定义内容");
  await userEvent.type(screen.getByRole("textbox", { name: "请选择或自行填写：自定义内容" }), "Markdown");
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  await waitFor(() => expect(getProjectRuntime("project-question-test").session.getState().messages[1].content).toBe("1. 请选择或自行填写：Markdown"));
});

it("submits structured form choices and typed details together", async () => {
  const structured = {
    ...question,
    fields: [
      { label: "通知事项", kind: "single" as const, options: ["价格调整", "系统维护"], required: true },
      { label: "需要说明", kind: "multiple" as const, options: ["时间", "影响范围"], required: false },
      { label: "发送日期", kind: "text" as const, options: [], required: true },
    ],
  };
  render(<HumanQuestionCard question={structured} text="请补充通知内容" />);
  await userEvent.click(screen.getByRole("radio", { name: "价格调整" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "时间" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "自己填写" }));
  await userEvent.type(screen.getByRole("textbox", { name: "需要说明：自定义内容" }), "老用户不受影响");
  await userEvent.type(screen.getByRole("textbox", { name: "发送日期" }), "10 月 1 日");
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    `${BACKEND_URL}/api/chat/task-1/human-reply`,
    expect.objectContaining({ body: JSON.stringify({
      question_id: "question-1",
      answer: "1. 通知事项：价格调整\n2. 需要说明：时间；老用户不受影响\n3. 发送日期：10 月 1 日",
    }) }),
  ));
});

it("renders Markdown in a short question", () => {
  const { container } = render(<HumanQuestionCard question={question} text="请确认 **通知事项** 和 *发送日期*。" />);
  expect(container.querySelector("strong")?.textContent).toBe("通知事项");
  expect(container.querySelector("em")?.textContent).toBe("发送日期");
  expect(screen.queryByText(/\*\*通知事项\*\*/)).not.toBeInTheDocument();
});

it("renders a long question once inside the expandable section", () => {
  const longQuestion = `请补充客户通知信息。\n\n1. **通知事项**：${"说明具体调整内容。".repeat(70)}`;
  const { container } = render(<HumanQuestionCard question={question} text={longQuestion} />);
  expect(screen.getByText("收起完整问题")).toBeInTheDocument();
  expect(container.querySelectorAll("strong")).toHaveLength(1);
  expect(container.querySelector("strong")?.textContent).toBe("通知事项");
  expect(screen.queryByText(/\*\*通知事项\*\*/)).not.toBeInTheDocument();
});

it("renders Markdown emphasis in form labels and options", () => {
  const formatted = {
    ...question,
    fields: [{ label: "**通知事项**", kind: "single" as const, options: ["*价格调整*"], required: true }],
  };
  const { container } = render(<HumanQuestionCard question={formatted} text="请选择" />);
  expect(container.querySelector(".human-question-field__title strong")?.textContent).toBe("通知事项");
  expect(container.querySelector("label em")?.textContent).toBe("价格调整");
});

it("turns a legacy numbered questionnaire into seven separate form fields", async () => {
  const legacy = {
    ...question,
    options: ["全量客户·价格调整通知", "全量客户·系统维护停机通知"],
  };
  const text = `请提供以下信息，我据此拟写客户通知邮件：

1. **通知事项**（核心内容）：要通知客户什么事？例如——
   - 价格/费率调整  - 系统维护停机
2. **关键要素**：涉及的具体数字、日期、时间、影响范围、需要客户采取的动作。
3. **收件人身份**：是哪些客户？以及对方联系人称呼。
4. **发件人身份**：以谁/哪个部门名义发出？
5. **语气风格**：正式公函 / 商务简洁 / 亲切友好。
6. **交付形式**：直接给邮件正文，还是写成文件？如需文件请说明格式：HTML / Markdown / Word。
7. **其他**：是否需要附件说明、是否需要中英双语。

选项参考（第 1 项常见场景）： A 价格调整通知|B 系统维护停机通知|C 服务升级通知`;
  render(<HumanQuestionCard question={legacy} text={text} />);

  expect(screen.getAllByRole("group")).toHaveLength(7);
  expect(screen.getByRole("radio", { name: "价格调整通知" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "关键要素" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "收件人身份" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "发件人身份" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "商务简洁" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Word 文件" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "其他" })).toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: "全量客户·价格调整通知" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("radio", { name: "价格调整通知" }));
  await userEvent.type(screen.getByRole("textbox", { name: "关键要素" }), "10 月 1 日生效");
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    `${BACKEND_URL}/api/chat/task-1/human-reply`,
    expect.objectContaining({ body: JSON.stringify({
      question_id: "question-1",
      answer: "1. 通知事项：价格调整通知\n2. 关键要素：10 月 1 日生效",
    }) }),
  ));
});
