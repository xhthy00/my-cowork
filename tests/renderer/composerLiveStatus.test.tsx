/**
 * @vitest-environment jsdom
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resolvePreset } from "thinking-orbs";

import ChatView from "../../renderer/src/components/ChatView";
import ComposerLiveStatus from "../../renderer/src/components/chat/ComposerLiveStatus";
import { dropAllProjectRuntimes } from "../../renderer/src/store/projectRuntime";
import { useSessionStore } from "../../renderer/src/store/session";
import { useSessionsStore } from "../../renderer/src/store/sessions";
import { toFileUrl, usePreviewStore } from '../../renderer/src/store/preview';
import { usePageTabStore } from '../../renderer/src/store/pageTab';

function stubCanvas() {
  const proto = HTMLCanvasElement.prototype as HTMLCanvasElement & {
    getContext: (id: string) => unknown;
  };
  vi.spyOn(proto, "getContext").mockReturnValue({
    setTransform() {},
    clearRect() {},
    beginPath() {},
    arc() {},
    fill() {},
    stroke() {},
    moveTo() {},
    lineTo() {},
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
  });
}

describe("ComposerLiveStatus", () => {
  beforeEach(() => {
    dropAllProjectRuntimes();
    useSessionsStore.setState({
      sessions: [],
      activeId: null,
      messagesById: {},
    });
    stubCanvas();
    window.api = {
      ...window.api,
      getBackendUrl: vi.fn().mockResolvedValue("http://127.0.0.1:8000"),
    };
  });

  it("thinking-orbs only ships size 20 / 64 — 18 throws after getContext", () => {
    expect(() => resolvePreset("breathing", 20)).not.toThrow();
    expect(() => resolvePreset("breathing", 18 as never)).toThrow();
  });

  it("renders on a fresh running session without crashing", () => {
    useSessionStore.getState().addUserMessage("帮我写一份周报");
    useSessionStore.getState().beginRun();
    expect(() => render(<ComposerLiveStatus />)).not.toThrow();
    expect(screen.getByRole("status")).toHaveTextContent(/思考中|开始分析/);
    expect(screen.getByRole("status")).toHaveTextContent(/已工作/);
    expect(screen.getByRole("status")).not.toHaveTextContent(/tokens/i);
  });

  it("ChatView survives empty-session → first send", () => {
    useSessionsStore.getState().createSession("新对话");
    useSessionStore.getState().addUserMessage("帮我写一份周报");
    useSessionStore.getState().beginRun();
    expect(() => render(<ChatView />)).not.toThrow();
    expect(screen.getByText("帮我写一份周报")).toBeInTheDocument();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(
      screen.getByLabelText(/开始分析任务，已工作/),
    ).toBeInTheDocument();
  });

  it('restores an existing HTML report card on a saved answer and opens preview with the keyboard', async () => {
    const path = '/Users/me/Documents/AIS/各地人工智能产业赋能中心 报告（合并版）.html';
    const verify = vi.fn().mockResolvedValue([path]);
    window.api = { ...window.api, existingPreviewFiles: verify };
    useSessionsStore.getState().createSession('生成合并报告');
    useSessionStore.setState({ runStatus: 'done', messages: [
      { id: 'u', role: 'user', content: '生成合并后的 HTML 报告' },
      { id: 'a', role: 'assistant', content: `报告已就绪，本轮复用了已生成的文件。\n交付文件：\`${path}\`` },
    ] });
    render(<ChatView />);
    const card = await screen.findByRole('button', { name: /各地人工智能产业赋能中心 报告（合并版）\.html/ });
    expect(verify).toHaveBeenCalledWith([path]);
    expect(useSessionStore.getState().messages.find(message => message.id === 'a')?.artifacts?.[0].path).toBe(path);
    card.focus();
    await userEvent.keyboard('{Enter}');
    await waitFor(() => expect(usePreviewStore.getState().tabs.some(tab => tab.type === 'browser' && tab.url === toFileUrl(path))).toBe(true));
    expect(usePageTabStore.getState().previewOpen).toBe(true);
  });

  it('returns a long conversation to its viewport bottom and resumes following new content', () => {
    useSessionStore.setState({ runStatus: 'done', messages: [
      { id: 'u', role: 'user', content: '阅读长报告' },
      { id: 'a', role: 'assistant', content: '报告正文' },
    ] });
    const { container } = render(<ChatView />);
    const viewport = container.querySelector<HTMLDivElement>('.messages')!;
    let height = 5000;
    Object.defineProperties(viewport, {
      scrollHeight: { get: () => height },
      clientHeight: { value: 600 },
    });
    viewport.scrollTop = 200;
    fireEvent.scroll(viewport);
    fireEvent.click(screen.getByRole('button', { name: '回到底部' }));
    expect(viewport.scrollTop).toBe(height);
    expect(screen.queryByRole('button', { name: '回到底部' })).not.toBeInTheDocument();
    height = 6000;
    act(() => useSessionStore.setState(state => ({ messages: state.messages.map(message =>
      message.id === 'a' ? { ...message, content: '报告正文\n\n新增内容' } : message) })));
    expect(viewport.scrollTop).toBe(height);
  });

  it('keeps the reading position when new content arrives while scrolled up', () => {
    useSessionStore.setState({ runStatus: 'done', messages: [
      { id: 'u', role: 'user', content: '阅读长报告' },
      { id: 'a', role: 'assistant', content: '报告正文' },
    ] });
    const { container } = render(<ChatView />);
    const viewport = container.querySelector<HTMLDivElement>('.messages')!;
    Object.defineProperties(viewport, { scrollHeight: { value: 5000 }, clientHeight: { value: 600 } });
    viewport.scrollTop = 200;
    fireEvent.scroll(viewport);
    act(() => useSessionStore.setState(state => ({ messages: state.messages.map(message =>
      message.id === 'a' ? { ...message, content: '报告正文\n\n新增内容' } : message) })));
    expect(viewport.scrollTop).toBe(200);
    expect(screen.getByRole('button', { name: '回到底部' })).toBeInTheDocument();
  });

  it('shows a harness clarification event as a form and submits to the original task', async () => {
    const originalFetch = globalThis.fetch;
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ questions: [{ question_id: 'fed-question' }] }) });
    globalThis.fetch = fetcher;
    try {
      useSessionsStore.getState().createSession('调研 FED 行业前景');
      useSessionStore.getState().addUserMessage('帮我调研 FED 行业前景');
      useSessionStore.getState().beginRun();
      render(<ChatView />);
      act(() => useSessionStore.getState().handleEvent({ type: 'human.ask', payload: {
        task_id: 'fed-task', question_id: 'fed-question', question: '请确认 FED 所指行业',
        fields: [
          { label: 'FED 所指行业', kind: 'single', options: ['场发射显示', '前端开发'], required: true },
          { label: '报告用途', kind: 'single', options: ['行业研究', '入行参考'], required: false },
          { label: '补充范围', kind: 'text', options: [], required: false },
        ],
      } }));
      expect(screen.getByRole('region', { name: '代理提问' })).toBeInTheDocument();
      expect(useSessionStore.getState().runStatus).toBe('running');
      await userEvent.click(screen.getByRole('radio', { name: '前端开发' }));
      await userEvent.click(screen.getByRole('button', { name: '下一步' }));
      await userEvent.click(screen.getByRole('radio', { name: '入行参考' }));
      await userEvent.click(screen.getByRole('button', { name: '下一步' }));
      await userEvent.click(screen.getByRole('button', { name: '提交并继续' }));
      await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/api/chat/fed-task/human-reply', expect.objectContaining({
          method: 'POST', body: JSON.stringify({ question_id: 'fed-question', answer: '1. FED 所指行业：前端开发\n2. 报告用途：入行参考' }),
        }),
      ));
      await waitFor(() => expect(screen.queryByRole('region', { name: '代理提问' })).not.toBeInTheDocument());
      expect(screen.getByRole('region', { name: '已补充的信息' })).toHaveTextContent('前端开发');
      expect(useSessionStore.getState().runStatus).toBe('running');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
