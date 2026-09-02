/**
 * @vitest-environment jsdom
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import KnowledgeView from "../../renderer/src/components/knowledge/KnowledgeView";

const BACKEND_URL = "http://127.0.0.1:8000";

describe("KnowledgeView", () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, sample_count: 1 }),
    }) as unknown as typeof fetch;
    window.api = {
      getBackendUrl: vi.fn().mockResolvedValue(BACKEND_URL),
      restartBackend: vi.fn().mockResolvedValue(BACKEND_URL),
      getKey: vi.fn().mockImplementation(async (account: string) => {
        if (account === "ima:client_id") return "saved-cid";
        if (account === "ima:api_key") return "saved-key";
        return null;
      }),
      setKey: vi.fn().mockResolvedValue(undefined),
      getModels: vi.fn().mockResolvedValue({ profiles: [], activeId: null }),
      upsertModel: vi.fn(),
      removeModel: vi.fn(),
      setActiveModel: vi.fn(),
      ipcPrintPDF: vi.fn(),
      ipcOpenPath: vi.fn(),
    };
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("loads saved ima credentials", async () => {
    render(<KnowledgeView />);
    await waitFor(() => {
      expect(screen.getByDisplayValue("saved-cid")).toBeTruthy();
      expect(screen.getByDisplayValue("saved-key")).toBeTruthy();
    });
  });

  it("saves credentials to keychain and restarts backend", async () => {
    window.api.getKey = vi.fn().mockResolvedValue(null);
    render(<KnowledgeView />);
    await waitFor(() => screen.getByRole("button", { name: "保存" }));

    const client = screen.getByPlaceholderText("ima-openapi-clientid");
    const key = screen.getByPlaceholderText("ima-openapi-apikey");
    await userEvent.clear(client);
    await userEvent.type(client, "new-cid");
    await userEvent.clear(key);
    await userEvent.type(key, "new-key");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(window.api.setKey).toHaveBeenCalledWith("ima:client_id", "new-cid");
      expect(window.api.setKey).toHaveBeenCalledWith("ima:api_key", "new-key");
      expect(window.api.restartBackend).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${BACKEND_URL}/api/ima/test`,
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("renders official logos for each source", async () => {
    render(<KnowledgeView />);
    await waitFor(() => screen.getByRole("button", { name: /腾讯 ima/ }));
    expect(screen.getAllByRole("img", { name: "腾讯 ima" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: "RAGFlow" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Notion" })).toBeTruthy();
  });

  it("lists upcoming sources as placeholders", async () => {
    render(<KnowledgeView />);
    await waitFor(() => screen.getByRole("button", { name: /腾讯 ima/ }));
    expect(screen.getByRole("button", { name: /RAGFlow/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Notion/ })).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /RAGFlow/ }));
    expect(screen.getAllByText("即将推出").length).toBeGreaterThan(0);
    expect(screen.queryByPlaceholderText("ima-openapi-clientid")).toBeNull();
  });
});

describe("parseBoundKnowledgeBases", () => {
  it("keeps unique id/name rows", async () => {
    const { parseBoundKnowledgeBases } = await import(
      "../../renderer/src/lib/knowledgeSources"
    );
    expect(
      parseBoundKnowledgeBases([
        { id: "kb1", name: "库", source: "ima" },
        { id: "kb1", name: "dup" },
        { name: "" },
      ]),
    ).toEqual([{ id: "kb1", name: "库", source: "ima" }]);
  });
});
