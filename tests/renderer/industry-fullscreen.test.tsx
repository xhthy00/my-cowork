/** @vitest-environment jsdom */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../../renderer/src/App";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import { useIndustryNavigation } from "../../renderer/src/store/industryNavigation";

vi.mock("@/components/ChatView", () => ({ default: () => <div>对话</div> }));
vi.mock("@/components/preview/PreviewPanel", () => ({ default: () => null }));
vi.mock("@/components/session/SessionSidePanel", () => ({ default: () => null }));
vi.mock("@/components/workspace/WorkspaceSessionLayout", () => ({ default: ({ chat }: any) => chat }));
vi.mock("@/components/settings/SettingsDialog", () => ({ default: () => null }));
vi.mock("@/components/shell/TopBar", () => ({ default: () => null }));
vi.mock("@/components/shell/ProjectSidebar", () => ({ default: () => <nav>宿主导航</nav> }));
vi.mock("@/components/hub/HubView", async () => ({
  default: (await import("@/components/hub/IndustryWorkbench")).default,
}));
vi.mock("@/store/desktopSessionSync", () => ({
  initDesktopSessionSync: () => {}, connectDesktopSessionSync: async () => {},
}));
vi.mock("@/api/automations", () => ({ automationApi: async () => ({ tasks: [] }) }));
vi.mock("@/api/industryAI", async (original) => ({
  ...await original<typeof import("@/api/industryAI")>(), watchAppTasks: () => () => {},
}));
vi.mock("react-resizable-panels", () => ({
  Group: ({ children, id }: any) => <div id={id}>{children}</div>,
  Panel: ({ children, id }: any) => <div id={id}>{children}</div>,
  Separator: () => <div role="separator" />,
}));

const app = { id: "cn.example.test", version: "1.0", generation: "g", status: "ready", enabled: true,
  manifest: { name: "业务插件", description: "业务页面", ui: { entry: "frontend/dist/index.html" } } };

beforeEach(() => {
  usePageTabStore.setState({ workspaceView: "hub", hubTab: "workbench", projectSidebarFolded: false });
  useIndustryNavigation.setState({ activeId: null, dirty: false, routes: {} });
  window.api = { ...window.api,
    getBackendUrl: vi.fn().mockResolvedValue("http://backend.test"),
    onBackendReady: vi.fn().mockReturnValue(() => {}),
    industryList: vi.fn().mockResolvedValue({ apps: [app] }),
  };
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("enters the plugin and returns without changing the user's sidebar layout", async () => {
  const savedLayout = JSON.stringify({ sidebar: 28, main: 72 });
  localStorage.setItem("my-cowork-workspace-shell-layout-v2", savedLayout);
  const view = render(<App />);
  const chrome = view.container.querySelector(".window")!;
  const sidebar = screen.getByRole("navigation");
  expect(chrome).toHaveAttribute("data-industry-fullscreen", "false");
  await userEvent.click(await screen.findByRole("button", { name: "打开 业务插件" }));
  const frame = screen.getByTitle("业务插件");
  expect(chrome).toHaveAttribute("data-industry-fullscreen", "true");
  expect(screen.getByRole("navigation")).toBe(sidebar);
  act(() => useIndustryNavigation.setState({ dirty: true }));
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  await userEvent.click(screen.getByRole("button", { name: "返回应用列表" }));
  expect(confirm).toHaveBeenCalledOnce();
  expect(chrome).toHaveAttribute("data-industry-fullscreen", "true");
  expect(screen.getByTitle("业务插件")).toBe(frame);
  confirm.mockReturnValue(true);
  await userEvent.click(screen.getByRole("button", { name: "返回应用列表" }));
  expect(chrome).toHaveAttribute("data-industry-fullscreen", "false");
  expect(screen.getByRole("navigation")).toBe(sidebar);
  expect(usePageTabStore.getState().projectSidebarFolded).toBe(false);
  expect(localStorage.getItem("my-cowork-workspace-shell-layout-v2")).toBe(savedLayout);
  expect(screen.getByRole("button", { name: "打开 业务插件" })).toBeInTheDocument();
});

it("keeps the chat shell visible when a plugin remains selected in another view", async () => {
  usePageTabStore.setState({ workspaceView: "workspace", projectSidebarFolded: true });
  useIndustryNavigation.setState({ activeId: app.id });
  const view = render(<App />);
  await screen.findByText("对话");
  expect(view.container.querySelector(".window")).toHaveAttribute("data-industry-fullscreen", "false");
  expect(screen.getByRole("navigation")).toBeInTheDocument();
  expect(usePageTabStore.getState().projectSidebarFolded).toBe(true);
});

it("preserves the live plugin frame when resizing across the compact breakpoint", async () => {
  const listeners = new Set<() => void>();
  const media = { matches: false,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", () => media);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "打开 业务插件" }));
  const frame = screen.getByTitle("业务插件");
  act(() => { media.matches = true; listeners.forEach(listener => listener()); });
  expect(screen.getByTitle("业务插件")).toBe(frame);
  expect(usePageTabStore.getState().projectSidebarFolded).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "返回应用列表" }));
  expect(screen.getByRole("button", { name: "打开 业务插件" })).toBeInTheDocument();
});
