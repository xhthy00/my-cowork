/** @vitest-environment jsdom */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import HumanQuestionCard, { HumanQuestionSummary } from "../../renderer/src/components/chat/HumanQuestionCard";
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
  HTMLElement.prototype.scrollIntoView = vi.fn();
  originalFetch = globalThis.fetch;
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true }) as unknown as typeof fetch;
  window.api = { ...window.api, getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL) };
  useSessionsStore.setState({ activeId: "project-question-test" });
  getProjectRuntime("project-question-test").session.setState({
    messages: [{ id: "ask-message", role: "assistant", content: "选哪种格式？", humanQuestion: question }],
  });
});

it("focuses and reveals the missing required field without scrolling its hidden input", async () => {
  render(<HumanQuestionCard question={question} text="选哪种格式？" />);
  const option = screen.getByRole("radio", { name: "PDF" });
  const focus = vi.spyOn(option, "focus");
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  expect(screen.getByRole("alert")).toHaveTextContent("请回答这一项");
  expect(focus).toHaveBeenCalledWith({ preventScroll: true });
  expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled();
  expect(globalThis.fetch).not.toHaveBeenCalled();
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
  expect(screen.getAllByRole("group")).toHaveLength(1);
  expect(screen.queryByRole("textbox", { name: "发送日期" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("radio", { name: "价格调整" }));
  await userEvent.click(screen.getByRole("button", { name: "下一步" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "时间" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "自己填写" }));
  await userEvent.type(screen.getByRole("textbox", { name: "需要说明：自定义内容" }), "老用户不受影响");
  await userEvent.click(screen.getByRole("button", { name: "上一题" }));
  expect(screen.getByRole("radio", { name: "价格调整" })).toBeChecked();
  await userEvent.click(screen.getByRole("button", { name: "下一步" }));
  expect(screen.getByRole("checkbox", { name: "时间" })).toBeChecked();
  expect(screen.getByRole("textbox", { name: "需要说明：自定义内容" })).toHaveValue("老用户不受影响");
  await userEvent.click(screen.getByRole("button", { name: "下一步" }));
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
  const { container } = render(<HumanQuestionSummary question={question} text="请确认 **通知事项** 和 *发送日期*。" />);
  expect(container.querySelector("strong")?.textContent).toBe("通知事项");
  expect(container.querySelector("em")?.textContent).toBe("发送日期");
  expect(screen.queryByText(/\*\*通知事项\*\*/)).not.toBeInTheDocument();
});

it("shows resolved answers and an expandable question in one compact record", async () => {
  const resolved = { ...question, status: "answered" as const,
    fields: [{ label: "收件人", kind: "text" as const, options: [], required: true },
      { label: "邮件目的", kind: "text" as const, options: [], required: true }],
    answer: "1. 收件人：领导\n2. 邮件目的：请假\n下周一" };
  const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) };
  vi.stubGlobal("navigator", { ...navigator, clipboard });
  const { container } = render(<HumanQuestionSummary question={resolved} text="请补充邮件信息" />);
  expect(screen.getByRole("region", { name: "已补充的信息" })).toHaveTextContent("领导");
  expect(container.querySelectorAll("dt")).toHaveLength(2);
  expect(container.querySelectorAll("dd")[1]).toHaveTextContent("请假 下周一");
  expect(container.querySelector("details")).not.toHaveAttribute("open");
  await userEvent.click(screen.getByRole("button", { name: "复制补充信息" }));
  expect(clipboard.writeText).toHaveBeenCalledWith(resolved.answer);
  vi.unstubAllGlobals();
});

it("preserves a free-form legacy reply in the combined record", () => {
  render(<HumanQuestionSummary question={{ ...question, status: "answered", answer: "用 Word，正文简洁一些。" }} text="选哪种格式？" />);
  expect(screen.getByText("用 Word，正文简洁一些。")).toBeInTheDocument();
});

it("renders a long question once inside the expandable section", () => {
  const longQuestion = `请补充客户通知信息。\n\n1. **通知事项**：${"说明具体调整内容。".repeat(70)}`;
  const { container } = render(<HumanQuestionSummary question={question} text={longQuestion} />);
  expect(screen.getByText("查看问题说明")).toBeInTheDocument();
  expect(container.querySelector("details")).not.toHaveAttribute("open");
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

  expect(screen.getAllByRole("group")).toHaveLength(1);
  expect(screen.getByLabelText("第 1 题，共 7 题")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "价格调整通知" })).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "关键要素" })).not.toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: "全量客户·价格调整通知" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("radio", { name: "价格调整通知" }));
  await userEvent.click(screen.getByRole("button", { name: "下一步" }));
  await userEvent.type(screen.getByRole("textbox", { name: "关键要素" }), "10 月 1 日生效");
  await userEvent.click(screen.getByRole("button", { name: "下一步" }));
  for (let i = 0; i < 5; i++) await userEvent.click(screen.getByRole("button", { name: "跳过" }));
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    `${BACKEND_URL}/api/chat/task-1/human-reply`,
    expect.objectContaining({ body: JSON.stringify({
      question_id: "question-1",
      answer: "1. 通知事项：价格调整通知\n2. 关键要素：10 月 1 日生效",
    }) }),
  ));
});


it("keeps a required question visible until it is answered", async () => {
  const fields = { ...question, fields: [
    { label: "收件人", kind: "text" as const, options: [], required: true },
    { label: "备注", kind: "text" as const, options: [], required: false },
  ] };
  render(<HumanQuestionCard question={fields} text="请补充" />);
  await userEvent.click(screen.getByRole("button", { name: "下一步" }));
  expect(screen.getByRole("alert")).toHaveTextContent("请回答这一项");
  expect(screen.getByRole("textbox", { name: "收件人" })).toHaveFocus();
  expect(screen.queryByRole("button", { name: "跳过" })).toBeNull();
  expect(globalThis.fetch).not.toHaveBeenCalled();
});

it("retains typed answers when the panel is closed and reopened", async () => {
  const { rerender } = render(<HumanQuestionCard question={question} text="选哪种格式？" />);
  await userEvent.click(screen.getByRole("radio", { name: "自己填写" }));
  await userEvent.type(screen.getByRole("textbox"), "Markdown");
  await act(async () => rerender(<HumanQuestionCard question={question} text="选哪种格式？" hidden />));
  expect(screen.queryByRole("textbox")).toBeNull();
  await act(async () => rerender(<HumanQuestionCard question={question} text="选哪种格式？" />));
  expect(screen.getByRole("textbox")).toHaveValue("Markdown");
});

it("continues the original task when every optional question is skipped", async () => {
  const optional = { ...question, fields: [
    { label: "备注", kind: "text" as const, options: [], required: false },
    { label: "格式", kind: "single" as const, options: ["Word"], required: false },
  ] };
  render(<HumanQuestionCard question={optional} text="请补充" />);
  await userEvent.click(screen.getByRole("button", { name: "跳过" }));
  await userEvent.click(screen.getByRole("button", { name: "跳过" }));
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    `${BACKEND_URL}/api/chat/task-1/human-reply`, expect.objectContaining({ body: JSON.stringify({
      question_id: "question-1", answer: "暂不补充，请根据已有信息继续处理，不确定的信息请标注待确认。",
    }) }),
  ));
});

it("keeps the selected answer after a failed submission and allows retry", async () => {
  vi.mocked(globalThis.fetch).mockResolvedValueOnce({ ok: false } as Response);
  render(<HumanQuestionCard question={question} text="选哪种格式？" />);
  await userEvent.click(screen.getByRole("radio", { name: "Word" }));
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("回复发送失败");
  expect(screen.getByRole("radio", { name: "Word" })).toBeChecked();
  await userEvent.click(screen.getByRole("button", { name: "提交并继续" }));
  await waitFor(() => expect(getProjectRuntime("project-question-test").session.getState().messages[0].humanQuestion?.status).toBe("answered"));
});
