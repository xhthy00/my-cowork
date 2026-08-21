/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resolvePreset } from "thinking-orbs";

import ChatView from "../../renderer/src/components/ChatView";
import ComposerLiveStatus from "../../renderer/src/components/chat/ComposerLiveStatus";
import { dropAllProjectRuntimes } from "../../renderer/src/store/projectRuntime";
import { useSessionStore } from "../../renderer/src/store/session";
import { useSessionsStore } from "../../renderer/src/store/sessions";

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
    expect(screen.getByRole("status")).toHaveTextContent(/tokens/i);
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
});
