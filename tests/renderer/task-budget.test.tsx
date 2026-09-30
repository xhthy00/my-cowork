/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BudgetEditor, PausedTaskBudget, SessionTaskBudget } from "../../renderer/src/components/chat/TaskBudget";
import { useSessionsStore } from "../../renderer/src/store/sessions";
import { useSessionStore } from "../../renderer/src/store/session";
import { dropAllProjectRuntimes } from "../../renderer/src/store/projectRuntime";
import { dispatchProjectEvent } from "../../renderer/src/store/livePark";

beforeEach(() => {
  dropAllProjectRuntimes();
  useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
  window.api = { getBackendUrl: vi.fn().mockResolvedValue("http://backend") } as any;
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("sends unlimited as null and inherited as undefined", async () => {
  const save = vi.fn();
  render(<BudgetEditor inherit onSave={save} />);
  fireEvent.click(screen.getByText("保存"));
  await waitFor(() => expect(save).toHaveBeenCalledWith(undefined));
  fireEvent.change(screen.getByLabelText("预算方式"), { target: { value: "unlimited" } });
  fireEvent.click(screen.getByText("保存"));
  await waitFor(() => expect(save).toHaveBeenCalledWith({ max_tokens: null }));
});

it("keeps paused usage with its conversation and resumes the original task", async () => {
  const one = useSessionsStore.getState().createSession("one");
  dispatchProjectEvent(one, { type: "graph.start", payload: { task_id: "original" } });
  dispatchProjectEvent(one, { type: "budget.paused", payload: { task_id: "original", tokens: 210000, max_tokens: 200000, required_tokens: 100 } });
  const two = useSessionsStore.getState().createSession("two");
  expect(useSessionStore.getState().budgetPaused).toBe(false);
  useSessionsStore.getState().setActive(one);
  expect(useSessionStore.getState().budgetPaused).toBe(true);
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  vi.stubGlobal("fetch", fetch);
  render(<PausedTaskBudget />);
  fireEvent.change(screen.getByLabelText("预算方式"), { target: { value: "unlimited" } });
  fireEvent.click(screen.getByText("增加额度并继续"));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("http://backend/api/chat/original/budget/resume", expect.objectContaining({ body: '{"max_tokens":null}' })));
  dispatchProjectEvent(one, { type: "budget.resumed", payload: { task_id: "original", tokens: 210000, max_tokens: null } });
  expect(useSessionStore.getState().budgetTokens).toBe(210000);
  expect(useSessionStore.getState().budgetMaxTokens).toBeNull();
  expect(useSessionStore.getState().budgetPaused).toBe(false);
  useSessionsStore.getState().setActive(two);
  expect(useSessionStore.getState().budgetTokens).toBe(0);
});

it("stores a conversation override without changing another conversation", async () => {
  const first = useSessionsStore.getState().createSession("one");
  const second = useSessionsStore.getState().createSession("two");
  render(<SessionTaskBudget running={false} />);
  fireEvent.click(screen.getByText("任务预算"));
  fireEvent.change(screen.getByLabelText("预算方式"), { target: { value: "custom" } });
  fireEvent.change(screen.getByLabelText("任务总额度"), { target: { value: "500000" } });
  fireEvent.click(screen.getByText("保存"));
  await waitFor(() => expect(useSessionsStore.getState().sessions.find((s) => s.id === second)?.taskBudget).toEqual({ max_tokens: 500000 }));
  expect(useSessionsStore.getState().sessions.find((s) => s.id === first)?.taskBudget).toBeUndefined();
});
