/** @vitest-environment jsdom */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChatSpaceSelect from "../../renderer/src/components/chat/ChatSpaceSelect";
import { useSessionStore } from "../../renderer/src/store/session";
import { useSessionsStore } from "../../renderer/src/store/sessions";
import { useSpacesStore } from "../../renderer/src/store/spaces";

const local = { id: "space-local", name: "本地工作区", sourceType: "blank" as const, rootPath: null, createdAt: 1, updatedAt: 1 };
const reports = { id: "space-report", name: "报告工作区", sourceType: "folder" as const, rootPath: "/tmp/reports", createdAt: 1, updatedAt: 1 };
let projectId: string;
let originalApi: typeof window.api;

async function openCreateMenu() {
  await userEvent.click(screen.getByRole("button", { name: "选择工作空间" }));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "搜索工作空间" })).toHaveFocus());
  const create = screen.getByRole("menuitem", { name: "创建工作空间" });
  create.focus();
  await userEvent.keyboard("{ArrowRight}");
}

describe("composer workspace management", () => {
  beforeEach(() => {
    originalApi = window.api;
    window.api = { ...window.api, getBackendUrl: vi.fn().mockResolvedValue(undefined), selectDirectory: vi.fn().mockResolvedValue("/tmp/client-reports") };
    useSpacesStore.setState({ spaces: [local, reports], activeSpaceId: local.id });
    useSessionsStore.setState({ sessions: [], activeId: null, messagesById: {} });
    useSessionStore.setState({ messages: [], runStatus: "idle" });
    projectId = useSessionsStore.getState().createProject("未发送的任务");
  });
  afterEach(() => { window.api = originalApi; });

  it("searches spaces, supports keyboard selection and restores trigger focus", async () => {
    render(<ChatSpaceSelect draft />);
    await userEvent.click(screen.getByRole("button", { name: "选择工作空间" }));
    const search = screen.getByRole("textbox", { name: "搜索工作空间" });
    await waitFor(() => expect(search).toHaveFocus());
    await userEvent.type(search, "报告");
    expect(screen.queryByRole("menuitem", { name: local.name })).toBeNull();
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(useSessionsStore.getState().activeId).toBe(projectId);
    expect(useSessionsStore.getState().sessions[0]).toMatchObject({ spaceId: reports.id, workdirMode: "direct-write" });
    await waitFor(() => expect(screen.getByRole("button", { name: "选择工作空间" })).toHaveFocus());
    await userEvent.click(screen.getByRole("button", { name: "选择工作空间" }));
    expect(screen.getByRole("textbox", { name: "搜索工作空间" })).toHaveValue("");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("creates a blank space and binds it to the existing draft", async () => {
    render(<ChatSpaceSelect draft />);
    await openCreateMenu();
    await userEvent.click(screen.getByRole("menuitem", { name: "从空白开始" }));
    const created = useSpacesStore.getState().spaces[0];
    expect(created).toMatchObject({ name: "空白工作区", sourceType: "blank", rootPath: null });
    expect(useSessionsStore.getState().sessions).toHaveLength(1);
    expect(useSessionsStore.getState().sessions[0]).toMatchObject({ id: projectId, spaceId: created.id, workdirMode: "artifact-only" });
    expect(screen.getByRole("button", { name: "选择工作空间" })).toHaveTextContent("空白工作区");
  });

  it("creates a folder space with direct-write mode", async () => {
    render(<ChatSpaceSelect draft />);
    await openCreateMenu();
    await userEvent.click(screen.getByRole("menuitem", { name: "选择文件夹…" }));
    await waitFor(() => expect(useSpacesStore.getState().spaces).toHaveLength(3));
    const created = useSpacesStore.getState().spaces[0];
    expect(created).toMatchObject({ name: "client-reports", rootPath: "/tmp/client-reports", sourceType: "folder" });
    expect(useSessionsStore.getState().sessions[0]).toMatchObject({ id: projectId, spaceId: created.id, workdirMode: "direct-write" });
  });

  it("keeps the current workspace when folder selection is cancelled", async () => {
    vi.mocked(window.api.selectDirectory).mockResolvedValue(null);
    render(<ChatSpaceSelect draft />);
    await openCreateMenu();
    await userEvent.click(screen.getByRole("menuitem", { name: "选择文件夹…" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "选择工作空间" })).not.toBeDisabled());
    expect(useSpacesStore.getState().spaces).toHaveLength(2);
    expect(useSessionsStore.getState().sessions[0].spaceId).toBe(local.id);
  });

  it("renames the selected space and returns focus from the dialog", async () => {
    render(<ChatSpaceSelect draft />);
    await userEvent.click(screen.getByRole("button", { name: "选择工作空间" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "重命名工作空间" }));
    expect(screen.getByRole("dialog", { name: "重命名工作空间" })).toBeVisible();
    const name = screen.getByRole("textbox", { name: "工作空间名称" });
    await waitFor(() => expect(name).toHaveFocus());
    await userEvent.clear(name);
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
    await userEvent.type(name, "  我的项目  {Enter}");
    expect(useSpacesStore.getState().spaces[0].name).toBe("我的项目");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "选择工作空间" })).toHaveFocus());
  });

  it("switches an existing conversation without changing its workspace or messages", async () => {
    const history = [{ id: "old-message", role: "user" as const, content: "保留原始对话" }];
    useSessionStore.setState({ messages: history });
    const target = useSessionsStore.getState().createProject("报告任务", { spaceId: reports.id, background: true });
    render(<ChatSpaceSelect draft={false} />);
    await userEvent.click(screen.getByRole("button", { name: "选择工作空间" }));
    await userEvent.click(screen.getByRole("menuitem", { name: reports.name }));
    expect(useSessionsStore.getState().activeId).toBe(target);
    expect(useSessionsStore.getState().sessions.find(p => p.id === projectId)?.spaceId).toBe(local.id);
    expect(useSessionsStore.getState().getMessages(projectId)).toEqual(history);
  });

  it("disables workspace operations while the composer is locked", async () => {
    render(<ChatSpaceSelect draft disabled />);
    await userEvent.click(screen.getByRole("button", { name: "选择工作空间" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
