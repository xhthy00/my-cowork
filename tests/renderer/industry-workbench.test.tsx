/** @vitest-environment jsdom */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IndustryWorkbench from "../../renderer/src/components/hub/IndustryWorkbench";
import { useIndustryNavigation } from "../../renderer/src/store/industryNavigation";
import type { IndustryStatus } from "../../renderer/src/window";

const app = {
  id: "cn.example.taskboard",
  version: "1.0.0",
  generation: "runtime-1",
  previous_version: null,
  enabled: true,
  status: "ready",
  manifest: {
    name: "任务管理样例",
    description: "本地任务管理",
    ui: { entry: "frontend/dist/index.html" },
  },
};

const industryList = vi.fn();
const industryInspect = vi.fn();
const industryInstall = vi.fn();
const industryRequest = vi.fn();
const selectFile = vi.fn();

beforeEach(() => {
  useIndustryNavigation.setState({ activeId: null, dirty: false, routes: {} });
  vi.clearAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  industryList.mockResolvedValue({ apps: [] });
  industryInspect.mockResolvedValue({
    sha256: "a".repeat(64),
    file_count: 7,
    expanded_bytes: 8000,
    trusted_code: true,
    manifest: {
      id: app.id,
      name: app.manifest.name,
      version: app.version,
      description: app.manifest.description,
      capabilities: { host_api: [] },
    },
  });
  industryInstall.mockResolvedValue({ id: app.id, version: app.version, requires_restart: true });
  industryRequest.mockResolvedValue({ tasks: [] });
  selectFile.mockResolvedValue({ success: true, files: [{ filePath: "/tmp/taskboard.zip", fileName: "taskboard.zip" }] });
  window.api = {
    ...window.api,
    industryList,
    industryInspect,
    industryInstall,
    industryRequest,
    selectFile,
    industryManage: vi.fn(),
    restartBackend: vi.fn(),
    onBackendReady: vi.fn().mockReturnValue(() => {}),
  };
});

describe("industry workbench", () => {
  it("previews trusted Python code before installing a ZIP", async () => {
    render(<IndustryWorkbench />);
    await userEvent.click(screen.getByRole("button", { name: "安装 ZIP" }));
    expect(await screen.findByText(/此应用可在本机运行代码，请仅安装你信任的来源/)).toBeTruthy();
    expect(industryInstall).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "确认安装" }));
    await waitFor(() => expect(industryInstall).toHaveBeenCalledWith("/tmp/taskboard.zip", "a".repeat(64)));
  });

  it("relays only the active iframe's app-scoped request", async () => {
    industryList.mockResolvedValue({ apps: [app] });
    render(<IndustryWorkbench />);
    await userEvent.click(await screen.findByRole("button", { name: "打开 任务管理样例" }));
    const frame = screen.getByTitle("任务管理样例") as HTMLIFrameElement;
    const bridgeToken = new URL(frame.src).searchParams.get("bridge");
    expect(bridgeToken).toBeTruthy();
    const source = frame.contentWindow;
    expect(source).toBeTruthy();
    const reply = vi.spyOn(source!, "postMessage");
    window.dispatchEvent(new MessageEvent("message", {
      origin: "mycowork-app://cn.example.taskboard",
      source,
      data: {
        channel: "mycowork-app/v1",
        appId: app.id,
        bridgeToken,
        id: "req-1",
        type: "request",
        operation: "app.request",
        method: "GET",
        path: "/tasks",
      },
    }));
    await waitFor(() => expect(industryRequest).toHaveBeenCalledWith(app.id, "GET", "/tasks", undefined, "runtime-1"));
    await waitFor(() => expect(reply).toHaveBeenCalledWith(expect.objectContaining({
      id: "req-1",
      ok: true,
    }), "mycowork-app://cn.example.taskboard"));
  });

  it("keeps package management in the app list while running", async () => {
    industryList.mockResolvedValue({ apps: [app] });
    render(<IndustryWorkbench />);
    await userEvent.click(await screen.findByRole("button", { name: "打开 任务管理样例" }));
    expect(screen.queryByRole("button", { name: "管理 任务管理样例" })).toBeNull();
    expect(screen.getByRole("button", { name: "AI 记录" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回应用列表" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "打开 任务管理样例" })));
    await userEvent.click(screen.getByRole("button", { name: "管理 任务管理样例" }));
    expect(await screen.findByRole("menuitem", { name: "从 ZIP 更新" })).toBeInTheDocument();
  });

  it("offers recovery instead of normal activation when recovery is required", async () => {
    industryList.mockResolvedValue({ apps: [{ ...app, status: "recovery_required" }] });
    render(<IndustryWorkbench />);
    await userEvent.click(await screen.findByRole("button", { name: "管理 任务管理样例" }));
    expect(await screen.findByRole("menuitem", { name: "重试恢复" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "启用", exact: true })).toBeNull();
  });

  it("does not offer a ZIP update for a source development app", async () => {
    industryList.mockResolvedValue({ apps: [{ ...app, dev_revision: "a".repeat(64) }] });
    render(<IndustryWorkbench />);
    await userEvent.click(await screen.findByRole("button", { name: "管理 任务管理样例" }));
    expect(screen.queryByRole("menuitem", { name: "从 ZIP 更新" })).toBeNull();
    expect(screen.getByText(/开发调试 · 可用/)).toBeInTheDocument();
  });

  it("offers an explicit update preview and cancels without applying it", async () => {
    industryList.mockResolvedValue({ apps: [app] });
    industryInspect.mockResolvedValue({
      sha256: "a".repeat(64), file_count: 7, current_version: "1.0.0",
      manifest: { ...app.manifest, id: app.id, version: "1.1.0", capabilities: { host_api: [] } },
    });
    render(<IndustryWorkbench />);
    await userEvent.click(await screen.findByRole("button", { name: "管理 任务管理样例" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "从 ZIP 更新" }));
    expect(await screen.findByText("1.0.0 → 1.1.0")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(industryInstall).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("restores host-owned progress when returning to the workbench", async () => {
    industryList.mockResolvedValue({ apps: [app], lifecycle: { busy: true, phase: "draining", appId: app.id, active: 1, tasks: ["current task"] } });
    window.api.industryCancel = vi.fn();
    render(<IndustryWorkbench />);
    expect(await screen.findByRole("status")).toHaveTextContent("等待 1 项工作结束");
    await userEvent.click(screen.getByRole("button", { name: "取消更新" }));
    expect(window.api.industryCancel).toHaveBeenCalledOnce();
    expect(window.api.restartBackend).not.toHaveBeenCalled();
  });

  it("does not replay an old success notice on entry but shows a new operation result", async () => {
    industryList.mockResolvedValue({ apps: [app], lifecycle: { busy: false, phase: "committed", generation: "old", message: "旧的启用成功提示" } });
    const subscribe = vi.fn((_callback: (status: IndustryStatus) => void) => () => {});
    window.api.onIndustryStatus = subscribe;
    render(<IndustryWorkbench />);
    await screen.findByRole("button", { name: "打开 任务管理样例" });
    expect(screen.queryByRole("status")).toBeNull();
    const next = { busy: false, phase: "committed", generation: "new", message: "本次更新完成" } as IndustryStatus;
    industryList.mockResolvedValue({ apps: [app], lifecycle: next });
    act(() => subscribe.mock.calls[0][0](next));
    expect(await screen.findByRole("status")).toHaveTextContent("本次更新完成");
  });
});
