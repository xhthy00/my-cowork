/**
 * @vitest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SettingsDialog from "../../renderer/src/components/settings/SettingsDialog";
import { usePageTabStore } from "../../renderer/src/store/pageTab";
import Settings from "../../renderer/src/components/settings/Settings";
import { useSettingsStore } from "../../renderer/src/store/settings";

const BACKEND_URL = "http://127.0.0.1:8000";

function resetStore() {
  useSettingsStore.setState({
    whitelist: ["~/Desktop", "~/Documents", "~/Downloads"],
    apiKey: "",
    appearance: "system",
    fontSize: 1,
  });
  document.documentElement.classList.remove("dark");
  document.documentElement.style.colorScheme = "light";
  document.documentElement.style.removeProperty("--ui-font-scale");
  document.documentElement.removeAttribute("data-font-size");
}

describe("Settings", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    window.localStorage.removeItem("my-cowork-settings");
    resetStore();
    usePageTabStore.setState({ settingsOpen: false, settingsSection: "general", workspaceView: "workspace", hubTab: "home" });
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true }) as unknown as typeof fetch;
    window.api = {
      getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL),
      restartBackend: vi.fn().mockResolvedValue(BACKEND_URL),
      getKey: vi.fn().mockResolvedValue(null),
      setKey: vi.fn().mockResolvedValue(undefined),
      getModels: vi.fn().mockResolvedValue({ profiles: [], activeId: null }),
      upsertModel: vi.fn().mockResolvedValue({
        profiles: [
          {
            id: "m1",
            name: "Anthropic",
            provider: "anthropic",
            model: "claude-sonnet-4-20250514",
            presetId: "anthropic",
            category: "cloud_byok",
            isValid: true,
          },
        ],
        activeId: "m1",
      }),
      removeModel: vi.fn(),
      setActiveModel: vi.fn(),
      validateModel: vi.fn().mockResolvedValue({ ok: true, latency_ms: 12 }),
      ipcPrintPDF: vi.fn(),
      ipcOpenPath: vi.fn(),
      startTunnel: vi.fn(),
      stopTunnel: vi.fn(),
      getTunnelUrl: vi.fn().mockResolvedValue(null),
      getUpdaterStatus: vi.fn().mockResolvedValue({
        state: "idle",
        currentVersion: "0.0.4",
      }),
      checkForUpdates: vi.fn(),
      downloadUpdate: vi.fn(),
      installUpdate: vi.fn(),
      onUpdaterStatus: vi.fn().mockReturnValue(() => {}),
      getKeepAwake: vi.fn().mockResolvedValue({ enabled: false, supported: true }),
      setKeepAwake: vi.fn().mockResolvedValue({ ok: true, enabled: true }),
    };
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    window.localStorage.removeItem("my-cowork-settings");
    document.documentElement.classList.remove("dark");
  });

  it("POSTs whitelist on save and updates zustand", async () => {
    render(<Settings />);

    await userEvent.click(screen.getByRole("button", { name: "隐私 / 白名单" }));
    await userEvent.click(screen.getByRole("button", { name: "保存白名单" }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${BACKEND_URL}/api/admin/whitelist`,
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            paths: ["~/Desktop", "~/Documents", "~/Downloads"],
          }),
        }),
      );
    });
    expect(useSettingsStore.getState().whitelist).toEqual([
      "~/Desktop",
      "~/Documents",
      "~/Downloads",
    ]);
  });

  it("updates zustand whitelist after editing and saving", async () => {
    render(<Settings />);

    await userEvent.click(screen.getByRole("button", { name: "隐私 / 白名单" }));
    await userEvent.type(screen.getByPlaceholderText("例如 ~/Projects"), "~/Projects");
    await userEvent.click(screen.getByRole("button", { name: "+ 添加目录…" }));
    await userEvent.click(screen.getByRole("button", { name: "保存白名单" }));

    await waitFor(() => {
      expect(useSettingsStore.getState().whitelist).toContain("~/Projects");
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${BACKEND_URL}/api/admin/whitelist`,
      expect.objectContaining({
        body: JSON.stringify({
          paths: ["~/Desktop", "~/Documents", "~/Downloads", "~/Projects"],
        }),
      }),
    );
  });

  it("validates then upserts a model via 保存", async () => {
    render(<Settings />);

    await userEvent.clear(screen.getByLabelText("API 密钥"));
    await userEvent.type(screen.getByLabelText("API 密钥"), "sk-test-key");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(window.api.validateModel).toHaveBeenCalled();
      expect(window.api.upsertModel).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Anthropic",
          provider: "anthropic",
          model: "claude-sonnet-4-20250514",
          apiKey: "sk-test-key",
          activate: true,
          isValid: true,
          presetId: "anthropic",
        }),
      );
    });
  });

  it("shows 检索 tab", async () => {
    render(<Settings />);
    expect(screen.getByRole("button", { name: "检索" })).toBeInTheDocument();
  });

  it("shows 远程连接 tab instead of 飞书远程", async () => {
    render(<Settings />);
    expect(screen.getByRole("button", { name: "远程连接" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "飞书远程" })).not.toBeInTheDocument();
  });

  it("merges appearance into system settings without duplicate navigation", () => {
    render(<Settings initialTab="general" />);
    expect(screen.queryByRole("button", { name: "连接器 / MCP" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "外观" })).not.toBeInTheDocument();
    expect(screen.getByText("界面主题")).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: "字体大小" })).toBeInTheDocument();
  });

  it("redirects the legacy appearance entry to system settings", () => {
    const { rerender } = render(<Settings initialTab="appearance" />);
    expect(screen.getByRole("button", { name: "系统设置" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("界面主题")).toBeInTheDocument();
    rerender(<Settings initialTab="model" />);
    rerender(<Settings initialTab="appearance" />);
    expect(screen.getByRole("button", { name: "系统设置" })).toHaveAttribute("aria-current", "page");
  });

  it("switches appearance from the general tab and persists the choice", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "系统设置" }));
    await userEvent.click(screen.getByRole("button", { name: "深色" }));

    expect(useSettingsStore.getState().appearance).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(screen.getByRole("button", { name: "深色" })).toHaveAttribute("aria-pressed", "true");
    expect(JSON.parse(window.localStorage.getItem("my-cowork-settings") || "{}").state.appearance).toBe("dark");

    await userEvent.click(screen.getByRole("button", { name: "浅色" }));
    expect(useSettingsStore.getState().appearance).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "跟随系统" }));
    expect(useSettingsStore.getState().appearance).toBe("system");
  });

  it("changes system font size from the general tab and persists the choice", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "系统设置" }));

    const slider = screen.getByRole("slider", { name: "字体大小" });
    expect(slider).toHaveValue("1");
    expect(screen.getByText("小")).toBeInTheDocument();
    expect(screen.getByText("默认")).toBeInTheDocument();
    expect(screen.getByText("大")).toBeInTheDocument();

    fireEvent.change(slider, { target: { value: "4" } });

    expect(useSettingsStore.getState().fontSize).toBe(4);
    expect(document.documentElement.getAttribute("data-font-size")).toBe("4");
    expect(document.documentElement.style.getPropertyValue("--ui-font-scale")).toBe("1.375");
    expect(JSON.parse(window.localStorage.getItem("my-cowork-settings") || "{}")).toEqual(
      expect.objectContaining({
        state: expect.objectContaining({ fontSize: 4 }),
      }),
    );
  });

  it("renders keep-awake on the general tab and toggles it", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "系统设置" }));

    const toggle = await screen.findByRole("switch", { name: "保持唤醒" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(
      screen.getByText(/阻止因空闲休眠/),
    ).toBeInTheDocument();

    await userEvent.click(toggle);
    await waitFor(() => {
      expect(window.api.setKeepAwake).toHaveBeenCalledWith({ enabled: true });
    });
  });

  it("opens API / 模型 when navigating to models", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "系统设置" }));
    expect(screen.getByRole("switch", { name: "保持唤醒" })).toBeInTheDocument();

    window.dispatchEvent(new CustomEvent("my-cowork:navigate", { detail: "models" }));

    expect(await screen.findByLabelText("API 密钥")).toBeInTheDocument();
  });

  it("shows 下载 when an update is available", async () => {
    let emitStatus: ((status: {
      state: string;
      currentVersion: string;
      availableVersion?: string;
      totalSize?: number;
    }) => void) | undefined;
    window.api.onUpdaterStatus = vi.fn((cb) => {
      emitStatus = cb;
      return () => {};
    });

    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "系统设置" }));
    expect(await screen.findByRole("button", { name: "检查更新" })).toBeInTheDocument();
    expect(await screen.findByText("当前版本 0.0.4")).toBeInTheDocument();

    emitStatus?.({
      state: "available",
      currentVersion: "0.0.4",
      availableVersion: "0.0.5",
      totalSize: 120 * 1024 * 1024,
    });
    expect(await screen.findByRole("button", { name: "下载" })).toBeInTheDocument();
    expect(screen.getByText(/发现新版本 0.0.5/)).toBeInTheDocument();
  });

  it("shows 下载中 while an update is downloading", async () => {
    let emitStatus: ((status: {
      state: string;
      currentVersion: string;
      percent?: number;
    }) => void) | undefined;
    window.api.onUpdaterStatus = vi.fn((cb) => {
      emitStatus = cb;
      return () => {};
    });

    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "系统设置" }));
    expect(await screen.findByRole("button", { name: "检查更新" })).toBeInTheDocument();
    emitStatus?.({ state: "downloading", currentVersion: "0.0.4", percent: 42 });
    expect(await screen.findByRole("button", { name: "下载中" })).toBeInTheDocument();
    expect(screen.getByText("正在下载 42%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下载中" })).toBeDisabled();
  });

  it("shows 重启安装 when an update is ready", async () => {
    let emitStatus: ((status: {
      state: string;
      currentVersion: string;
      availableVersion?: string;
    }) => void) | undefined;
    window.api.onUpdaterStatus = vi.fn((cb) => {
      emitStatus = cb;
      return () => {};
    });
    window.api.installUpdate = vi.fn().mockResolvedValue({ ok: true });

    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "系统设置" }));
    expect(await screen.findByRole("button", { name: "检查更新" })).toBeInTheDocument();
    emitStatus?.({
      state: "downloaded",
      currentVersion: "0.0.4",
      availableVersion: "0.0.5",
    });
    const install = await screen.findByRole("button", { name: "重启安装" });
    expect(screen.getByText("下载完成，重启后安装")).toBeInTheDocument();
    await userEvent.click(install);
    expect(window.api.installUpdate).toHaveBeenCalled();
  });

  it("shows 定时任务 in the settings nav", async () => {
    render(<Settings />);
    expect(screen.getByRole("button", { name: "定时任务" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "定时任务" }));
    expect(await screen.findByRole("button", { name: "刷新定时任务" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "新建" }));
    expect(screen.getByLabelText("任务名称")).toBeInTheDocument();
    expect(screen.getByLabelText("执行内容")).toBeInTheDocument();
  });

  it("opens settings over the current page and restores focus and draft on Escape", async () => {
    render(<><input aria-label="保留的草稿" defaultValue="整理报告" /><button onClick={() => usePageTabStore.getState().openSettings()}>打开设置</button><SettingsDialog /></>);
    const trigger = screen.getByRole("button", { name: "打开设置" });
    await userEvent.click(trigger);
    expect(await screen.findByRole("dialog", { name: "设置" })).toBeVisible();
    expect(screen.getByRole("slider", { name: "字体大小" })).toBeVisible();
    expect(usePageTabStore.getState().workspaceView).toBe("workspace");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("textbox", { name: "保留的草稿" })).toHaveValue("整理报告");
    expect(trigger).toHaveFocus();
  });

  it("opens the model section in the dialog without changing the underlying page", async () => {
    usePageTabStore.getState().openSettings("model");
    render(<SettingsDialog />);
    expect(await screen.findByLabelText("API 密钥")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "关闭设置" }));
    expect(usePageTabStore.getState()).toMatchObject({ settingsOpen: false, workspaceView: "workspace", hubTab: "home" });
  });

  it("keeps knowledge configuration and browser controls available inside settings", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ open: false, status: "closed", url: "", title: "" }) }) as typeof fetch;
    window.api.getCdpBrowsers = vi.fn().mockResolvedValue([]);
    window.api.connectCdpBrowser = vi.fn().mockResolvedValue({ port: 9333 });
    usePageTabStore.setState({ browserSection: "agent", hubTab: "agents", agentsSection: "skill-store", workspaceView: "hub" });
    usePageTabStore.getState().openSettings("knowledge");
    render(<SettingsDialog />);
    expect(await screen.findByPlaceholderText("ima-openapi-clientid")).toBeVisible();
    expect(screen.getByRole("button", { name: "资料库", exact: true })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "浏览器", exact: true }));
    expect(await screen.findByText("暂无浏览器页面")).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "外部 CDP" }));
    await userEvent.clear(screen.getByPlaceholderText("端口"));
    await userEvent.type(screen.getByPlaceholderText("端口"), "9333");
    await userEvent.click(screen.getByRole("button", { name: "连接已有浏览器" }));
    await waitFor(() => expect(window.api.connectCdpBrowser).toHaveBeenCalledWith(9333));
    await userEvent.click(screen.getByRole("button", { name: "关闭设置" }));
    expect(usePageTabStore.getState()).toMatchObject({ settingsOpen: false, workspaceView: "hub", hubTab: "agents", agentsSection: "skill-store" });
  });
});
