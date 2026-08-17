/**
 * Adapted from eigent: ProjectPageSidebar + SpaceSwitchDropdown
 * Two-level nav: Space switcher + Projects in active Space.
 */
import {
  LayoutGrid,
  Plus,
  Radio,
  FolderOpen,
  Trash2,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";

import AlertDialog from "@/components/ui/alertDialog";
import { cn } from "@/lib/utils";
import {
  PROJECT_SIDEBAR_EXPANDED_WIDTH_PX,
  PROJECT_SIDEBAR_RAIL_WIDTH_PX,
} from "@/components/session/sessionSidePanelLayout";
import SpaceSwitchDropdown from "@/components/shell/SpaceSwitchDropdown";
import { usePageTabStore } from "@/store/pageTab";
import {
  ensureActiveSession,
  useSessionsStore,
} from "@/store/sessions";
import { useSpacesStore } from "@/store/spaces";

function navTabClass(active: boolean) {
  return cn(
    "h-8 w-full min-w-0 shrink-0 rounded-xl flex items-center justify-start gap-3 px-3 text-left outline-none overflow-hidden transition-colors duration-200",
    "text-ds-text-neutral-muted-default text-body-sm font-medium",
    "hover:bg-ds-bg-neutral-subtle-default",
    active && "bg-ds-bg-neutral-subtle-default",
  );
}

export default function ProjectSidebar({
  fill = false,
}: {
  /** When true, fill parent (resizable panel); otherwise fixed Eigent rail/expanded width. */
  fill?: boolean;
}) {
  const folded = usePageTabStore((s) => s.projectSidebarFolded);
  const workspaceView = usePageTabStore((s) => s.workspaceView);
  const setWorkspaceView = usePageTabStore((s) => s.setWorkspaceView);
  const setHubTab = usePageTabStore((s) => s.setHubTab);
  const sessions = useSessionsStore((s) => s.sessions);
  const activeId = useSessionsStore((s) => s.activeId);
  const setActive = useSessionsStore((s) => s.setActive);
  const createProject = useSessionsStore((s) => s.createProject);
  const deleteSession = useSessionsStore((s) => s.deleteSession);
  const spaces = useSpacesStore((s) => s.spaces);
  const activeSpaceId = useSpacesStore((s) => s.activeSpaceId);
  const setActiveSpace = useSpacesStore((s) => s.setActiveSpace);
  const createBlankSpace = useSpacesStore((s) => s.createBlankSpace);
  const createFolderSpace = useSpacesStore((s) => s.createFolderSpace);
  const renameSpace = useSpacesStore((s) => s.renameSpace);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  const deleteTarget = deleteId
    ? sessions.find((s) => s.id === deleteId)
    : null;

  const width = folded
    ? PROJECT_SIDEBAR_RAIL_WIDTH_PX
    : PROJECT_SIDEBAR_EXPANDED_WIDTH_PX;

  const activeSpace = spaces.find((s) => s.id === activeSpaceId) ?? spaces[0];
  const projects = useMemo(
    () => sessions.filter((s) => s.spaceId === (activeSpaceId || activeSpace?.id)),
    [sessions, activeSpaceId, activeSpace?.id],
  );

  function selectSpace(spaceId: string) {
    setActiveSpace(spaceId);
    const first = useSessionsStore.getState().projectsForSpace(spaceId)[0];
    if (first) setActive(first.id);
    else createProject("新对话", { spaceId });
    setWorkspaceView("workspace");
  }

  async function pickFolderSpace() {
    const dir = await window.api.selectDirectory?.();
    if (!dir) return;
    const name = dir.split(/[/\\]/).filter(Boolean).pop() || "文件夹工作区";
    const spaceId = createFolderSpace(name, dir);
    createProject(name, { spaceId, workdirMode: "direct-write" });
    setWorkspaceView("workspace");
  }

  function openRename() {
    setRenameValue(activeSpace?.name || "");
    setRenameOpen(true);
  }

  function confirmRename() {
    const next = renameValue.trim();
    if (!next || !activeSpaceId) return;
    renameSpace(activeSpaceId, next);
    setRenameOpen(false);
  }

  return (
    <aside
      className="box-border flex h-full min-h-0 shrink-0 flex-col overflow-hidden rounded-2xl bg-ds-bg-neutral-default-default p-1"
      style={fill && !folded ? { width: "100%" } : { width }}
    >
      <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
        <nav className="flex w-full shrink-0 flex-col gap-1">
          <button
            type="button"
            title="工作区"
            className={cn(
              navTabClass(workspaceView === "workspace"),
              folded && "justify-center px-0 gap-0",
            )}
            onClick={() => {
              setWorkspaceView("workspace");
              ensureActiveSession();
            }}
          >
            <LayoutGrid className="h-4 w-4 shrink-0 text-ds-icon-neutral-muted-default" />
            {!folded && <span className="min-w-0 flex-1 truncate">工作区</span>}
          </button>
          <button
            type="button"
            title="上下文"
            className={cn(navTabClass(false), folded && "justify-center px-0 gap-0")}
            onClick={() => {
              setHubTab("agents");
              usePageTabStore.getState().setAgentsSection("memory");
            }}
          >
            <FolderOpen className="h-4 w-4 shrink-0 text-ds-icon-neutral-muted-default" />
            {!folded && (
              <>
                <span className="min-w-0 flex-1 truncate">上下文</span>
                <span className="rounded-md bg-ds-bg-neutral-subtle-default px-1.5 py-0.5 text-[10px] font-semibold text-ds-text-neutral-muted-default">
                  本地
                </span>
              </>
            )}
          </button>
          <button
            type="button"
            title="定时"
            className={cn(navTabClass(false), folded && "justify-center px-0 gap-0")}
            onClick={() => setHubTab("settings")}
          >
            <Zap className="h-4 w-4 shrink-0 text-ds-icon-neutral-muted-default" />
            {!folded && <span className="min-w-0 flex-1 truncate">定时</span>}
          </button>
          <button
            type="button"
            title="调度"
            className={cn(navTabClass(false), folded && "justify-center px-0 gap-0")}
            onClick={() => setHubTab("connectors")}
          >
            <Radio className="h-4 w-4 shrink-0 text-ds-icon-neutral-muted-default" />
            {!folded && <span className="min-w-0 flex-1 truncate">调度</span>}
          </button>
        </nav>

        <div className="my-2 px-3">
          <div className="h-px w-full bg-ds-border-neutral-default-default" />
        </div>

        {!folded && (
          <>
            <div className="mb-2 px-1">
              <SpaceSwitchDropdown
                spaces={spaces}
                activeSpaceId={activeSpaceId}
                onSpaceSelect={selectSpace}
                onRenameSpace={openRename}
                onStartFromScratch={() => {
                  const id = createBlankSpace();
                  createProject("新对话", {
                    spaceId: id,
                    workdirMode: "artifact-only",
                  });
                  setWorkspaceView("workspace");
                }}
                onSelectFolder={() => void pickFolderSpace()}
              />
            </div>

            <button
              type="button"
              className={cn(navTabClass(false), "mb-1")}
              onClick={() => {
                createProject();
                setWorkspaceView("workspace");
              }}
            >
              <Plus className="h-4 w-4 shrink-0" />
              <span>新建项目</span>
            </button>

            <div className="mb-1 px-3 pt-1 text-[11px] font-semibold tracking-wide text-ds-text-neutral-subtle-default">
              项目
            </div>
            <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-0.5">
              {projects.map((s) => (
                <div
                  key={s.id}
                  className={cn(
                    "group/project relative flex w-full items-center gap-1 rounded-xl pr-1 transition-colors",
                    activeId === s.id
                      ? "bg-ds-bg-neutral-subtle-default text-ds-text-neutral-default-default"
                      : "text-ds-text-neutral-muted-default hover:bg-ds-bg-neutral-subtle-default",
                  )}
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 rounded-xl px-3 py-2 text-left text-body-sm"
                    onClick={() => {
                      setActive(s.id);
                      setWorkspaceView("workspace");
                    }}
                  >
                    {s.status === "done" ? (
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-ds-icon-status-completed-default text-[10px] text-white">
                        ✓
                      </span>
                    ) : (
                      <span className="h-4 w-4 shrink-0 rounded-full border border-ds-border-neutral-default-default" />
                    )}
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {s.title}
                    </span>
                  </button>
                  <button
                    type="button"
                    title="删除项目"
                    aria-label={`删除 ${s.title}`}
                    className="mr-1 hidden h-7 w-7 shrink-0 items-center justify-center rounded-lg text-ds-text-neutral-subtle-default hover:bg-ds-bg-neutral-strong-default hover:text-ds-text-error-default-default group-hover/project:flex"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteId(s.id);
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
              {projects.length === 0 && (
                <p className="px-3 py-2 text-xs text-ds-text-neutral-subtle-default">
                  暂无项目
                </p>
              )}
            </div>
          </>
        )}
      </div>

      <AlertDialog
        open={deleteId != null}
        title="删除项目"
        description={
          deleteTarget
            ? `确定删除「${deleteTarget.title}」？对话记录将一并清除，此操作不可撤销。`
            : "确定删除该项目？此操作不可撤销。"
        }
        confirmLabel="删除"
        confirmVariant="destructive"
        onCancel={() => setDeleteId(null)}
        onConfirm={() => {
          if (!deleteId) return;
          const id = deleteId;
          setDeleteId(null);
          deleteSession(id);
          if (!useSessionsStore.getState().activeId) {
            ensureActiveSession();
          }
        }}
      />

      <AlertDialog
        open={renameOpen}
        title="重命名工作空间"
        confirmLabel="保存"
        confirmDisabled={!renameValue.trim()}
        onCancel={() => setRenameOpen(false)}
        onConfirm={confirmRename}
      >
        <input
          autoFocus
          value={renameValue}
          placeholder="工作空间名称"
          className="h-9 w-full rounded-xl border border-ds-border-neutral-subtle-default bg-ds-bg-neutral-subtle-default px-3 text-sm outline-none focus:ring-2 focus:ring-ds-ring-neutral-subtle-default"
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && renameValue.trim()) confirmRename();
          }}
        />
      </AlertDialog>
    </aside>
  );
}
