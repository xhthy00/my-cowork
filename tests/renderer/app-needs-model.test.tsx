/** @vitest-environment jsdom */

import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../renderer/src/components/ChatView", () => ({ default: () => null }));
vi.mock("../../renderer/src/components/preview/PreviewPanel", () => ({ default: () => null }));
vi.mock("../../renderer/src/components/session/SessionSidePanel", () => ({ default: () => null }));
vi.mock("../../renderer/src/components/hub/HubView", () => ({ default: () => <div>hub</div> }));
vi.mock("../../renderer/src/components/shell/ProjectSidebar", () => ({ default: () => null }));
vi.mock("../../renderer/src/components/shell/TopBar", () => ({ default: () => null }));
vi.mock("../../renderer/src/components/TitleBar", () => ({ default: () => null }));
vi.mock("../../renderer/src/components/StartupSplash", () => ({ default: () => <div>splash</div> }));
vi.mock("../../renderer/src/store/desktopSessionSync", () => ({
  initDesktopSessionSync: vi.fn(),
  connectDesktopSessionSync: vi.fn(),
}));

import App from "../../renderer/src/App";
import { usePageTabStore } from "../../renderer/src/store/pageTab";

describe("first launch without an API key", () => {
  let readyCb: ((url: string) => void) | undefined;
  const navigations: string[] = [];
  const onNav = (e: Event) => navigations.push((e as CustomEvent<string>).detail);

  beforeEach(() => {
    readyCb = undefined;
    navigations.length = 0;
    window.addEventListener("my-cowork:navigate", onNav);
    usePageTabStore.setState({ workspaceView: "hub", hubTab: "home" });
    window.api = {
      getBackendUrl: vi.fn().mockResolvedValue(""),
      getBackendStatus: vi.fn().mockResolvedValue({ state: "needs-model", error: "" }),
      onBackendNeedsModel: vi.fn(() => () => {}),
      onBackendReady: vi.fn((cb: (url: string) => void) => {
        readyCb = cb;
        return () => {};
      }),
    } as unknown as typeof window.api;
  });

  afterEach(() => {
    window.removeEventListener("my-cowork:navigate", onNav);
  });

  it("skips the blocking splash, opens model settings, and clears the hint once ready", async () => {
    render(<App />);

    const hint = await screen.findByText(/还没有配置模型/);
    expect(hint).toBeInTheDocument();
    expect(screen.queryByText("splash")).not.toBeInTheDocument();
    expect(navigations).toEqual(["models"]);

    readyCb?.("http://127.0.0.1:8000");
    await waitFor(() => expect(screen.queryByText(/还没有配置模型/)).not.toBeInTheDocument());
    expect(screen.queryByText("splash")).not.toBeInTheDocument();
  });

  it("still shows the splash while a configured backend is starting", async () => {
    window.api.getBackendStatus = vi.fn().mockResolvedValue({ state: "starting", error: "" });
    render(<App />);
    expect(screen.getByText("splash")).toBeInTheDocument();
    await waitFor(() => expect(window.api.getBackendStatus).toHaveBeenCalled());
    expect(screen.queryByText(/还没有配置模型/)).not.toBeInTheDocument();
  });

  it("does not let a stale initial snapshot overwrite a ready event", async () => {
    let resolveStatus!: (value: { state: "needs-model"; error: string }) => void;
    window.api.getBackendStatus = vi.fn(() => new Promise((resolve) => { resolveStatus = resolve; }));
    render(<App />);
    await act(async () => { readyCb?.("http://127.0.0.1:8000"); });
    await act(async () => { resolveStatus({ state: "needs-model", error: "" }); });
    expect(screen.queryByText("splash")).not.toBeInTheDocument();
    expect(screen.queryByText(/还没有配置模型/)).not.toBeInTheDocument();
  });

  it("keeps the failure screen even if a stale URL response is nonempty", async () => {
    window.api.getBackendUrl = vi.fn().mockResolvedValue("http://127.0.0.1:8000");
    window.api.getBackendStatus = vi.fn().mockResolvedValue({ state: "failed", error: "startup failed" });
    render(<App />);
    await act(async () => {});
    expect(screen.getByText("splash")).toBeInTheDocument();
  });
});
