/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import McpConnectorsPanel from "../../renderer/src/components/settings/McpConnectorsPanel";

const BACKEND_URL = "http://127.0.0.1:8000";

type ServerMap = Record<string, Record<string, unknown>>;

describe("McpConnectorsPanel", () => {
  let originalFetch: typeof fetch;
  let servers: ServerMap;

  beforeEach(() => {
    servers = {};
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || "GET").toUpperCase();
      const json = async () =>
        init?.body ? (JSON.parse(String(init.body)) as { mcpServers?: ServerMap }) : {};

      if (url.endsWith("/api/mcp/servers") && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ mcpServers: { ...servers } }),
        } as Response;
      }
      if (url.endsWith("/api/mcp/servers") && method === "PUT") {
        const body = await json();
        servers = { ...(body.mcpServers || {}) };
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, mcpServers: servers, connected: {} }),
        } as Response;
      }
      if (url.endsWith("/api/mcp/import") && method === "POST") {
        const body = await json();
        servers = { ...servers, ...(body.mcpServers || {}) };
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, mcpServers: servers, connected: {} }),
        } as Response;
      }
      if (url.includes("/api/mcp/servers/") && url.endsWith("/test") && method === "POST") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, tools: ["mcp.playwright.navigate"] }),
        } as Response;
      }
      return { ok: false, status: 404, json: async () => ({ detail: "missing" }) } as Response;
    }) as unknown as typeof fetch;

    window.api = {
      ...window.api,
      getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL),
    };
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("imports local JSON via POST /api/mcp/import", async () => {
    render(<McpConnectorsPanel />);
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(`${BACKEND_URL}/api/mcp/servers`);
    });

    await userEvent.click(screen.getByRole("button", { name: "添加" }));
    await userEvent.click(screen.getByRole("button", { name: "导入" }));

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
      const importCall = calls.find(
        ([u, init]) =>
          String(u).endsWith("/api/mcp/import") &&
          String((init as RequestInit | undefined)?.method) === "POST",
      );
      expect(importCall).toBeTruthy();
      const body = JSON.parse(String((importCall?.[1] as RequestInit).body));
      expect(body.mcpServers["sequential-thinking"].command).toBe("npx");
    });
  });

  it("imports a remote URL as { url }", async () => {
    render(<McpConnectorsPanel />);
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(`${BACKEND_URL}/api/mcp/servers`);
    });

    await userEvent.click(screen.getByRole("button", { name: "添加" }));
    await userEvent.click(screen.getByRole("tab", { name: "远程 URL" }));
    await userEvent.type(screen.getByPlaceholderText("playwright"), "playwright");
    await userEvent.type(
      screen.getByPlaceholderText("https://example.com/mcp"),
      "https://example.com/mcp",
    );
    await userEvent.click(screen.getByRole("button", { name: "导入" }));

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
      const importCall = calls.find(
        ([u, init]) =>
          String(u).endsWith("/api/mcp/import") &&
          String((init as RequestInit | undefined)?.method) === "POST",
      );
      expect(importCall).toBeTruthy();
      const body = JSON.parse(String((importCall?.[1] as RequestInit).body));
      expect(body.mcpServers.playwright).toEqual({ url: "https://example.com/mcp" });
    });
  });

  it("shows a toast after a successful test", async () => {
    servers = {
      playwright: { url: "https://example.com/mcp", enabled: true },
    };
    render(<McpConnectorsPanel />);
    await waitFor(() => {
      expect(screen.getByText("playwright")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: "测试" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("playwright 测试通过，1 个工具");
    });
  });
});