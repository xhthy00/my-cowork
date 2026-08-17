/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Settings from "../../renderer/src/components/settings/Settings";
import { useSettingsStore } from "../../renderer/src/store/settings";

const BACKEND_URL = "http://127.0.0.1:8000";

function resetStore() {
  useSettingsStore.setState({
    whitelist: ["~/Desktop", "~/Documents", "~/Downloads"],
    apiKey: "",
    appearance: "system",
  });
  document.documentElement.classList.remove("dark");
  document.documentElement.style.colorScheme = "light";
}

describe("Settings", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    window.localStorage.removeItem("my-cowork-settings");
    resetStore();
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
      checkForUpdates: vi.fn(),
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

  it("shows 远程连接 tab instead of 飞书远程", async () => {
    render(<Settings />);
    expect(screen.getByRole("button", { name: "远程连接" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "飞书远程" })).not.toBeInTheDocument();
  });

  it("switches appearance and persists the choice", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByRole("button", { name: "外观" }));
    await userEvent.click(screen.getByRole("button", { name: "深色" }));

    expect(useSettingsStore.getState().appearance).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "浅色" }));
    expect(useSettingsStore.getState().appearance).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "跟随系统" }));
    expect(useSettingsStore.getState().appearance).toBe("system");
  });
});
