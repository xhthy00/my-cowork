/** @vitest-environment jsdom */
import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ModelsPanel from "../../renderer/src/components/settings/ModelsPanel";
import type { ModelsState } from "../../renderer/src/window";

let state: ModelsState;
beforeEach(() => {
  state = {
    connections: [
      {
        id: "c1",
        name: "公司连接",
        provider: "openai_compat",
        presetId: "openai",
        baseUrl: "https://api.openai.com/v1",
        keyAccount: "connection:c1",
      },
    ],
    profiles: [
      {
        id: "m1",
        connectionId: "c1",
        name: "日常工作",
        model: "gpt-test",
        provider: "openai_compat",
        presetId: "openai",
        baseUrl: "https://api.openai.com/v1",
      },
    ],
    activeId: "m1",
    compactionRatio: 0.8,
  };
  window.api = {
    getModels: vi.fn(async () => structuredClone(state)),
    getModelCatalog: vi.fn(async () => ({
      updatedAt: "2026-09-28",
      models: [
        {
          id: "openai/gpt-test",
          provider: "openai",
          model: "gpt-test",
          name: "GPT Test",
          reasoning: true,
          options: [{ type: "effort", values: ["low", "high"] }],
          context: 128000,
        },
      ],
    })),
    upsertModel: vi.fn(async (p) => {
      state.profiles = [{ ...p, id: p.id || "m2" }];
      return structuredClone(state);
    }),
    upsertConnection: vi.fn(async (c) => {
      state.connections = [c];
      return structuredClone(state);
    }),
    setCompactionRatio: vi.fn(async (r) => {
      state.compactionRatio = r;
      return structuredClone(state);
    }),
    validateModel: vi.fn(async () => ({ ok: true, latency_ms: 12 })),
    getKey: vi.fn(async () => "test-key"),
  } as unknown as typeof window.api;
});

describe("model configuration redesign", () => {
  it("keeps reasoning and catalog maintenance out of settings", async () => {
    render(<ModelsPanel />);
    await screen.findByText("公司连接");
    expect(screen.queryByText("模型能力目录")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "上下文" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("自动压缩阈值")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "编辑 日常工作" }),
    );
    expect(screen.queryByLabelText("思考强度")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("上下文窗口")).not.toBeInTheDocument();
  });
  it("returns keyboard focus to the model after closing its editor", async () => {
    render(<ModelsPanel />);
    const edit = await screen.findByRole("button", { name: "编辑 日常工作" });
    await userEvent.click(edit);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(edit).toHaveFocus());
  });

  it("preserves an existing fractional compression threshold", async () => {
    state.compactionRatio = 0.805;
    render(<ModelsPanel />);
    await screen.findByText("公司连接");
    expect(screen.getByLabelText("自动压缩阈值")).toHaveValue(80.5);
    expect(screen.getByRole("button", { name: "保存阈值" })).toBeDisabled();
  });
  it("does not mistake a credential reference for an actually saved key", async () => {
    vi.mocked(window.api.getKey).mockResolvedValue(null);
    render(<ModelsPanel />);
    expect(await screen.findByText(/未配置密钥/)).toBeInTheDocument();
    expect(screen.queryByText(/密钥已配置/)).not.toBeInTheDocument();
  });
  it("shows grouped summaries and opens forms only on demand", async () => {
    render(<ModelsPanel />);
    expect(await screen.findByText("公司连接")).toBeInTheDocument();
    expect(screen.getAllByText("日常工作")[0]).toBeInTheDocument();
    expect(screen.queryByLabelText("API 密钥")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("模型 ID")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "编辑 日常工作" }),
    );
    expect(
      screen.getByRole("dialog", { name: "编辑模型" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("模型 ID")).toHaveValue("gpt-test");
  });

  it("saves model changes without changing its shared connection or default", async () => {
    render(<ModelsPanel />);
    await userEvent.click(
      await screen.findByRole("button", { name: "编辑 日常工作" }),
    );
    fireEvent.change(screen.getByLabelText("模型显示名称"), {
      target: { value: "新名称" },
    });
    await userEvent.click(screen.getByRole("button", { name: "保存模型" }));
    await waitFor(() =>
      expect(window.api.upsertModel).toHaveBeenCalledWith(
        expect.objectContaining({
          id: "m1",
          connectionId: "c1",
          name: "新名称",
          activate: false,
        }),
      ),
    );
    expect(window.api.upsertConnection).not.toHaveBeenCalled();
    expect(state.activeId).toBe("m1");
  });

  it("rejects invalid context without writing configuration", async () => {
    render(<ModelsPanel />);
    await userEvent.click(
      await screen.findByRole("button", { name: "调整上下文 日常工作" }),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("窗口设置方式 日常工作"),
      "custom",
    );
    const input = screen.getByLabelText("上下文窗口 日常工作");
    fireEvent.change(input, { target: { value: "100" } });
    await userEvent.click(screen.getByRole("button", { name: "保存窗口" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("4096");
    expect(window.api.upsertModel).not.toHaveBeenCalled();
  });

  it("protects an unsaved draft on Escape and offers explicit discard", async () => {
    render(<ModelsPanel />);
    await userEvent.click(
      await screen.findByRole("button", { name: "编辑 日常工作" }),
    );
    fireEvent.change(screen.getByLabelText("模型显示名称"), {
      target: { value: "未保存" },
    });
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    expect(screen.getByLabelText("模型显示名称")).toHaveValue("未保存");
    await userEvent.click(screen.getByRole("button", { name: "关闭编辑面板" }));
    await userEvent.click(screen.getByRole("button", { name: "放弃修改" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(window.api.upsertModel).not.toHaveBeenCalled();
  });

  it("tests saved model parameters and requires saving a changed draft first", async () => {
    render(<ModelsPanel />);
    await userEvent.click(
      await screen.findByRole("button", { name: "编辑 日常工作" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(window.api.validateModel).toHaveBeenCalledWith(
      expect.objectContaining({ profileId: "m1" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("12 ms");
    fireEvent.change(screen.getByLabelText("模型显示名称"), {
      target: { value: "high" },
    });
    expect(screen.getByRole("button", { name: "测试连接" })).toBeDisabled();
  });

  it("keeps failed test feedback inside the editor and preserves the form", async () => {
    vi.mocked(window.api.validateModel!).mockResolvedValue({
      ok: false,
      error: "服务拒绝参数",
    });
    render(<ModelsPanel />);
    await userEvent.click(
      await screen.findByRole("button", { name: "编辑 日常工作" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(
      await within(screen.getByRole("dialog")).findByRole("alert"),
    ).toHaveTextContent("服务拒绝参数");
    expect(screen.getByLabelText("模型 ID")).toHaveValue("gpt-test");
  });

  it("edits connection separately without saving a model", async () => {
    render(<ModelsPanel />);
    await userEvent.click(
      await screen.findByRole("button", { name: "编辑连接 公司连接" }),
    );
    fireEvent.change(screen.getByLabelText("API 密钥"), {
      target: { value: "new-test-key" },
    });
    await userEvent.click(screen.getByRole("button", { name: "保存连接" }));
    await waitFor(() =>
      expect(window.api.upsertConnection).toHaveBeenCalledWith(
        expect.objectContaining({ id: "c1", apiKey: "new-test-key" }),
      ),
    );
    expect(window.api.upsertModel).not.toHaveBeenCalled();
  });

  it("saves the compression threshold explicitly", async () => {
    render(<ModelsPanel />);
    await screen.findByText("公司连接");
    fireEvent.change(screen.getByLabelText("自动压缩阈值"), {
      target: { value: "70" },
    });
    expect(screen.getByLabelText("自动压缩阈值")).toHaveValue(70);
    await userEvent.click(screen.getByRole("button", { name: "保存阈值" }));
    await waitFor(() =>
      expect(window.api.setCompactionRatio).toHaveBeenCalledWith(0.7),
    );
  });
});

it("shows actual context values until editing and cancels without saving", async () => {
  render(<ModelsPanel />);
  expect(
    await screen.findByRole("table", { name: "模型上下文窗口" }),
  ).toBeInTheDocument();
  expect(await screen.findByText("128,000")).toBeInTheDocument();
  expect(
    screen.queryByLabelText("上下文窗口 日常工作"),
  ).not.toBeInTheDocument();
  const adjust = screen.getByRole("button", { name: "调整上下文 日常工作" });
  await userEvent.click(adjust);
  expect(screen.getByLabelText("上下文窗口 日常工作")).toBeDisabled();
  await userEvent.selectOptions(
    screen.getByLabelText("窗口设置方式 日常工作"),
    "custom",
  );
  fireEvent.change(screen.getByLabelText("上下文窗口 日常工作"), {
    target: { value: "64000" },
  });
  await userEvent.click(screen.getByRole("button", { name: "取消调整" }));
  expect(window.api.upsertModel).not.toHaveBeenCalled();
  await waitFor(() => expect(adjust).toHaveFocus());
  expect(
    screen.queryByLabelText("上下文窗口 日常工作"),
  ).not.toBeInTheDocument();
  await userEvent.click(adjust);
  expect(screen.getByLabelText("窗口设置方式 日常工作")).toHaveValue("auto");
});

it("explicitly saves a custom window and restores automatic capacity", async () => {
  render(<ModelsPanel />);
  await userEvent.click(
    await screen.findByRole("button", { name: "调整上下文 日常工作" }),
  );
  await userEvent.selectOptions(
    screen.getByLabelText("窗口设置方式 日常工作"),
    "custom",
  );
  fireEvent.change(screen.getByLabelText("上下文窗口 日常工作"), {
    target: { value: "64000" },
  });
  await userEvent.click(screen.getByRole("button", { name: "保存窗口" }));
  expect(await screen.findByText("64,000")).toBeInTheDocument();
  expect(screen.getByText("自定义")).toBeInTheDocument();
  expect(window.api.upsertModel).toHaveBeenLastCalledWith(
    expect.objectContaining({ contextWindow: 64000, activate: false }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "调整上下文 日常工作" }),
  );
  await userEvent.selectOptions(
    screen.getByLabelText("窗口设置方式 日常工作"),
    "auto",
  );
  await userEvent.click(screen.getByRole("button", { name: "保存窗口" }));
  expect(await screen.findByText("128,000")).toBeInTheDocument();
  expect(window.api.upsertModel).toHaveBeenLastCalledWith(
    expect.objectContaining({ contextWindow: undefined, activate: false }),
  );
});
