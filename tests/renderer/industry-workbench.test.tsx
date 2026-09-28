/** @vitest-environment jsdom */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IndustryWorkbench from "../../renderer/src/components/hub/IndustryWorkbench";

const app = {
  id: "cn.example.taskboard",
  version: "1.0.0",
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
  vi.clearAllMocks();
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
    expect(await screen.findByText(/此 ZIP 含可在 MyCowork 后端进程中运行的 Python 代码/)).toBeTruthy();
    expect(industryInstall).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "确认安装" }));
    await waitFor(() => expect(industryInstall).toHaveBeenCalledWith("/tmp/taskboard.zip", "a".repeat(64)));
  });

  it("relays only the active iframe's app-scoped request", async () => {
    industryList.mockResolvedValue({ apps: [app] });
    render(<IndustryWorkbench />);
    await userEvent.click(await screen.findByRole("button", { name: /任务管理样例/ }));
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
    await waitFor(() => expect(industryRequest).toHaveBeenCalledWith(app.id, "GET", "/tasks", undefined));
    await waitFor(() => expect(reply).toHaveBeenCalledWith(expect.objectContaining({
      id: "req-1",
      ok: true,
    }), "mycowork-app://cn.example.taskboard"));
  });
});
